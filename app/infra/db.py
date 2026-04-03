"""
Capa de abstracción de base de datos.

Backend seleccionado via env var:
  - DATABASE_URL=postgresql://user:pass@host:5432/dbname  →  PostgreSQL
  - DATABASE_URL vacío o no definido                      →  SQLite  (default, sin cambios)

MIGRACIÓN SIN RIESGO:
  En producción con SQLite actual, no cambiar nada. El comportamiento es idéntico al anterior.
  Para activar PostgreSQL en un nuevo servidor: export DATABASE_URL=postgresql://...
"""
import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL.startswith("postgresql"):
    try:
        import psycopg2
        import psycopg2.extras
        BACKEND = "postgresql"
        # Log sin exponer credenciales (solo host/db)
        _safe_url = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
        logger.info("Database backend: PostgreSQL (%s)", _safe_url)
    except ImportError as exc:
        raise RuntimeError(
            "DATABASE_URL apunta a PostgreSQL pero psycopg2-binary no está instalado. "
            "Añade psycopg2-binary a requirements.txt"
        ) from exc
else:
    BACKEND = "sqlite"
    if DATABASE_URL:
        logger.warning("DATABASE_URL configurado pero no empieza con 'postgresql://'. Usando SQLite.")
    else:
        logger.info("Database backend: SQLite")

# ---------------------------------------------------------------------------
# Helpers SQL cross-backend para aritmética de fechas sobre la columna created_at
# ---------------------------------------------------------------------------
if BACKEND == "postgresql":
    # Minutos transcurridos desde created_at
    SQL_MINUTES_SINCE_CREATED = (
        "EXTRACT(EPOCH FROM ("
        "NOW() AT TIME ZONE 'UTC' - created_at::timestamptz"
        "))::INTEGER / 60"
    )
    # Días enteros transcurridos desde created_at
    SQL_DAYS_SINCE_CREATED = (
        "EXTRACT(DAY FROM AGE("
        "NOW() AT TIME ZONE 'UTC', created_at::timestamptz"
        "))::INTEGER"
    )
    # Días restantes para el límite de 14 días del plan free (mínimo 0)
    SQL_DAYS_REMAINING_14 = (
        "GREATEST(0, 14 - EXTRACT(DAY FROM AGE("
        "NOW() AT TIME ZONE 'UTC', created_at::timestamptz"
        "))::INTEGER)"
    )
else:
    SQL_MINUTES_SINCE_CREATED = (
        "CAST((julianday('now') - julianday(created_at)) * 1440 AS INTEGER)"
    )
    SQL_DAYS_SINCE_CREATED = (
        "CAST(julianday('now') - julianday(created_at) AS INTEGER)"
    )
    SQL_DAYS_REMAINING_14 = (
        "MAX(0, 14 - CAST((julianday('now') - julianday(created_at)) AS INTEGER))"
    )

# ---------------------------------------------------------------------------
# Cursor adapter unificado
# ---------------------------------------------------------------------------

class _AdaptedCursor:
    """
    Wrappea el cursor nativo para proveer una interfaz unificada.

    SQLite   → pass-through; expone lastrowid del cursor nativo.
    PostgreSQL → traduce '?' → '%s'; captura lastrowid vía SELECT lastval().
    """

    __slots__ = ("_cur", "_backend", "_lastrowid")

    def __init__(self, cursor, backend: str):
        self._cur = cursor
        self._backend = backend
        self._lastrowid: Optional[int] = None

    def execute(self, sql: str, params=None):
        if self._backend == "postgresql":
            sql = sql.replace("?", "%s")
            if params is not None:
                self._cur.execute(sql, params)
            else:
                self._cur.execute(sql)
            # Capturar lastrowid para INSERT en tablas con SERIAL
            if sql.strip().upper().startswith("INSERT"):
                try:
                    self._cur.execute("SELECT lastval()")
                    row = self._cur.fetchone()
                    # RealDictCursor devuelve {"lastval": N}
                    self._lastrowid = row["lastval"] if row else None
                except Exception:
                    self._lastrowid = None
        else:
            if params is not None:
                self._cur.execute(sql, params)
            else:
                self._cur.execute(sql)
            self._lastrowid = self._cur.lastrowid
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def lastrowid(self) -> Optional[int]:
        return self._lastrowid

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount


# ---------------------------------------------------------------------------
# Connection adapter unificado
# ---------------------------------------------------------------------------

class _ConnectionAdapter:
    """
    Wrappea una conexión nativa (sqlite3.Connection o psycopg2.connection)
    y expone la interfaz que usan todos los repositorios:
      conn.cursor() → _AdaptedCursor
      conn.commit()
      conn.rollback()
      conn.close()
      conn.execute()  # solo para PRAGMA (no-op en PostgreSQL)
    """

    def __init__(self, conn, backend: str):
        self._conn = conn
        self._backend = backend

    def cursor(self) -> _AdaptedCursor:
        if self._backend == "postgresql":
            raw = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            raw = self._conn.cursor()
        return _AdaptedCursor(raw, self._backend)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def execute(self, sql: str, params=None):
        """
        Compatibilidad con sentencias PRAGMA de SQLite.
        En PostgreSQL es un no-op.
        """
        if self._backend == "postgresql":
            return self
        raw_cur = self._conn.cursor()
        if params is not None:
            raw_cur.execute(sql, params)
        else:
            raw_cur.execute(sql)
        return _AdaptedCursor(raw_cur, self._backend)


# ---------------------------------------------------------------------------
# Pool thread-local para PostgreSQL
# ---------------------------------------------------------------------------

_pg_local = threading.local()


def get_pg_connection() -> _ConnectionAdapter:
    """
    Devuelve la conexión PostgreSQL del hilo actual (thread-local pool).
    Crea una nueva si no existe.
    """
    conn = getattr(_pg_local, "conn", None)
    if conn is None:
        raw = psycopg2.connect(DATABASE_URL)
        raw.autocommit = False
        conn = _ConnectionAdapter(raw, "postgresql")
        _pg_local.conn = conn
        logger.debug(
            "Nueva conexión PostgreSQL para hilo '%s'",
            threading.current_thread().name,
        )
    return conn


def reset_pg_connection() -> None:
    """
    Cierra y elimina la conexión thread-local de PostgreSQL.
    Llamar tras init_db() o tras un error de conexión.
    """
    conn = getattr(_pg_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _pg_local.conn = None
