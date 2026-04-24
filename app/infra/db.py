"""
Capa de PERSISTENCIA DEFINITIVA (PostgreSQL Only).
HostingGuard - Phase 3: Professional Connection Pooling.
"""
import logging
import os
import threading
from typing import Optional
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

logger = logging.getLogger(__name__)

_TESTING = os.getenv("TESTING") == "1"

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL and not _TESTING:
    raise RuntimeError("Falta la variable de entorno DATABASE_URL (obligatoria para PostgreSQL).")

# Global Pool Singleton
_pool: Optional[ThreadedConnectionPool] = None
_pool_lock = threading.Lock()

def init_db_pool(minconn: int = 2, maxconn: int = 20):
    """Inicializa el pool de conexiones global (llamado en main.py al startup)."""
    global _pool
    if _TESTING:
        logger.info("[db] TESTING mode — skipping pool init")
        return
    with _pool_lock:
        if _pool is None:
            try:
                logger.info("Inicializando ThreadedConnectionPool (min=%d, max=%d)", minconn, maxconn)
                _pool = ThreadedConnectionPool(
                    minconn=minconn,
                    maxconn=maxconn,
                    dsn=DATABASE_URL,
                    cursor_factory=psycopg2.extras.RealDictCursor
                )
            except Exception:
                logger.exception("Error fatal al inicializar el pool de base de datos")
                raise

# ---------------------------------------------------------------------------
# Helpers SQL POSTGRESQL para aritmética de fechas (Constantes)
# ---------------------------------------------------------------------------
SQL_MINUTES_SINCE_CREATED = "EXTRACT(EPOCH FROM (NOW() AT TIME ZONE 'UTC' - created_at::timestamptz))::INTEGER / 60"
SQL_DAYS_SINCE_CREATED = "EXTRACT(DAY FROM AGE(NOW() AT TIME ZONE 'UTC', created_at::timestamptz))::INTEGER"
SQL_DAYS_REMAINING_14 = "GREATEST(0, 14 - EXTRACT(DAY FROM AGE(NOW() AT TIME ZONE 'UTC', created_at::timestamptz))::INTEGER)"

# ---------------------------------------------------------------------------
# Wrappers de Compatibilidad
# ---------------------------------------------------------------------------

class _AdaptedCursor:
    """Wrapper para mantener compatibilidad con la lógica de ejecución previa."""
    __slots__ = ("_cur", "_lastrowid")

    def __init__(self, cursor):
        self._cur = cursor
        self._lastrowid = None

    def execute(self, sql: str, params=None):
        if params is not None:
            self._cur.execute(sql, params)
        else:
            self._cur.execute(sql)

        # Capturar RETURNING automáticamente — consume el resultado una sola vez
        # para que los repos que llaman fetchone() explícitamente no pierdan el row.
        # NOTA: los repos que usan RETURNING + fetchone() siguen funcionando igual
        # porque _lastrowid se llena aquí y ellos obtienen None en su fetchone().
        # Para compatibilidad total, consumimos el row solo si el repo NO va a llamar
        # fetchone() — esto no es posible detectarlo aquí, por lo tanto NO consumimos
        # el cursor: dejamos _lastrowid como referencia al primer campo del próximo fetchone().
        self._lastrowid = None
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        if row and self._lastrowid is None:
            # Capturar el primer valor como lastrowid (backfill para código legado)
            self._lastrowid = list(row.values())[0] if row else None
        return row

    def fetchall(self): return self._cur.fetchall()

    @property
    def rowcount(self) -> int: return self._cur.rowcount

    @property
    def lastrowid(self): return self._lastrowid


class _ConnectionWrapper:
    """Wrapper para que los repositorios no necesiten cambiar su lógica de .commit() .rollback()"""
    def __init__(self, conn):
        self._conn = conn
        self._released = False

    def cursor(self) -> _AdaptedCursor:
        return _AdaptedCursor(self._conn.cursor())

    def commit(self): self._conn.commit()
    def rollback(self): self._conn.rollback()
    def execute(self, sql: str, params=None): return self.cursor().execute(sql, params)

    def close(self):
        if not self._released:
            release_connection(self)
            self._released = True

# ---------------------------------------------------------------------------
# Gestión de Pool
# ---------------------------------------------------------------------------

def get_connection() -> _ConnectionWrapper:
    """Obtiene una conexión del pool global. Reintenta hasta 3 veces si el pool está agotado."""
    global _pool
    if _TESTING:
        raise RuntimeError(
            "get_connection() called in TESTING mode — mock the repository instead of using the real DB."
        )
    if _pool is None:
        init_db_pool()

    import time as _time
    last_exc: Exception = RuntimeError("pool unavailable")
    pool = _pool  # local ref satisfies type checker (not None after init_db_pool)
    assert pool is not None, "pool should be initialized"

    for attempt in range(3):
        try:
            conn = pool.getconn()
            conn.autocommit = False
            # Descartar conexiones stale (cerradas por el servidor tras idle timeout)
            if conn.closed:
                pool.putconn(conn, close=True)
                raise psycopg2.OperationalError("stale connection discarded")
            return _ConnectionWrapper(conn)
        except psycopg2.OperationalError as exc:
            # Solo reintentamos errores de CONEXIÓN (pool agotado, idle timeout, network).
            # Nunca reintentamos IntegrityError, ProgrammingError, etc. — esos son errores
            # de datos que una segunda ejecución repetiría con el mismo resultado.
            last_exc = exc
            if attempt < 2:
                _time.sleep(0.1 * (attempt + 1))
                logger.warning("get_connection retry %d/3: %s", attempt + 1, exc)
        except Exception:
            # Cualquier otro error (constraint, sintaxis, etc.) — no reintentar, relanzar.
            raise

    logger.error("No se pudo obtener una conexión del pool tras 3 intentos: %s", last_exc)
    raise last_exc

def release_connection(wrapper: _ConnectionWrapper):
    """Devuelve la conexión al pool. Idempotente — double-release es no-op."""
    global _pool
    if _pool and wrapper and hasattr(wrapper, "_conn"):
        if getattr(wrapper, "_released", False):
            return
        try:
            _pool.putconn(wrapper._conn)
            wrapper._released = True
        except Exception:
            logger.error("Error al devolver conexión al pool")

def reset_pg_connection():
    """Alias para compatibilidad con código antiguo que intentaba limpiar el thread-local."""
    pass


def set_user_context(conn: _ConnectionWrapper, user_id: int, is_admin: bool = False) -> None:
    """Set transaction-local RLS context before running user-scoped queries.

    Uses set_config(..., TRUE) which means the setting is LOCAL to the current
    transaction — it resets automatically on COMMIT or ROLLBACK. Safe with a
    shared connection pool because the context never leaks between requests.

    RLS enforcement:
    - With current postgres superuser: RLS is BYPASSED (policies exist but not enforced).
    - To fully activate: create a restricted `app_user` DB role and point DATABASE_URL
      at it. Admin endpoints call with is_admin=True to bypass tenant isolation.

    Usage:
        conn = get_connection()
        set_user_context(conn, user_id=42)
        conn.cursor().execute("SELECT * FROM hostings WHERE user_id = %s", (42,))
        release_connection(conn)
    """
    cur = conn._conn.cursor()
    cur.execute(
        "SELECT set_config('app.current_user_id', %s, TRUE)",
        (str(user_id),),
    )
    cur.execute(
        "SELECT set_config('app.is_admin', %s, TRUE)",
        ("1" if is_admin else "0",),
    )
