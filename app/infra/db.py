"""
Capa de PERSISTENCIA DEFINITIVA (PostgreSQL Only).
HostingGuard - Phase 2 cleanup.
"""
import logging
import os
import threading
from typing import Optional
import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

# La URL de base de datos es ahora obligatoria para el funcionamiento del sistema.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Falta la variable de entorno DATABASE_URL (obligatoria para PostgreSQL).")

BACKEND = "postgresql"

# ---------------------------------------------------------------------------
# Helpers SQL POSTGRESQL para aritmética de fechas
# ---------------------------------------------------------------------------
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
# Días restantes para el límite de 14 días del plan free
SQL_DAYS_REMAINING_14 = (
    "GREATEST(0, 14 - EXTRACT(DAY FROM AGE("
    "NOW() AT TIME ZONE 'UTC', created_at::timestamptz"
    "))::INTEGER)"
)

# ---------------------------------------------------------------------------
# Cursor y Conexión (Wrappers para RealDictCursor y estabilidad)
# ---------------------------------------------------------------------------

class _AdaptedCursor:
    """Interface unificada para cursores de Postgres con soporte de Factories."""
    __slots__ = ("_cur", "_lastrowid")

    def __init__(self, cursor):
        self._cur = cursor
        self._lastrowid: Optional[int] = None

    def execute(self, sql: str, params=None):
        # En esta fase ya NO reemplazamos '?' -> '%s'. 
        # El código debe usar '%s' directamente.
        if params is not None:
            self._cur.execute(sql, params)
        else:
            self._cur.execute(sql)
            
        # Captura automática de lastval() solo en INSERTs
        if sql.strip().upper().startswith("INSERT"):
            try:
                # Intentamos lastval() si el código no usó RETURNING
                if "RETURNING" not in sql.upper():
                    self._cur.execute("SELECT lastval()")
                    row = self._cur.fetchone()
                    # RealDictCursor devuelve {"lastval": N}
                    self._lastrowid = row["lastval"] if row else None
            except Exception:
                self._lastrowid = None
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

class _ConnectionAdapter:
    """Wrapper de conexión PostgreSQL."""
    def __init__(self, conn):
        self._conn = conn

    def cursor(self) -> _AdaptedCursor:
        # Usamos siempre RealDictCursor para compatibilidad con lógica dict[key]
        raw = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        return _AdaptedCursor(raw)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def execute(self, sql: str, params=None):
        """No-op para PRAGMAs legacy, soporte para queries rápidas."""
        if "PRAGMA" in sql.upper():
            return self
        cur = self.cursor()
        return cur.execute(sql, params)

# ---------------------------------------------------------------------------
# Pool thread-local
# ---------------------------------------------------------------------------
_pg_local = threading.local()

def get_pg_connection() -> _ConnectionAdapter:
    """Obtiene o crea una conexión Postgres para el hilo actual."""
    conn = getattr(_pg_local, "conn", None)
    if conn is not None and conn._conn.closed != 0:
        logger.warning("Reconectando Postgres en hilo '%s'", threading.current_thread().name)
        _pg_local.conn = None
        conn = None
        
    if conn is None:
        raw = psycopg2.connect(DATABASE_URL)
        raw.autocommit = False
        conn = _ConnectionAdapter(raw)
        _pg_local.conn = conn
    return conn

def reset_pg_connection() -> None:
    conn = getattr(_pg_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except:
            pass
        _pg_local.conn = None

def get_connection() -> _ConnectionAdapter:
    """Alias para compatibilidad global."""
    return get_pg_connection()
