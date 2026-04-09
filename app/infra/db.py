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

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Falta la variable de entorno DATABASE_URL (obligatoria para PostgreSQL).")

# Global Pool Singleton
_pool: Optional[ThreadedConnectionPool] = None
_pool_lock = threading.Lock()

def init_db_pool(minconn: int = 2, maxconn: int = 20):
    """Inicializa el pool de conexiones global (llamado en main.py al startup)."""
    global _pool
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
    __slots__ = ("_cur",)
    def __init__(self, cursor):
        self._cur = cursor

    def execute(self, sql: str, params=None):
        if params is not None:
            self._cur.execute(sql, params)
        else:
            self._cur.execute(sql)
        return self

    def fetchone(self): return self._cur.fetchone()
    def fetchall(self): return self._cur.fetchall()
    
    @property
    def rowcount(self) -> int: return self._cur.rowcount
    
    @property
    def lastrowid(self) -> Optional[int]: return None # Deprecated

class _ConnectionWrapper:
    """Wrapper para que los repositorios no necesiten cambiar su lógica de .commit() .rollback()"""
    def __init__(self, conn):
        self._conn = conn

    def cursor(self) -> _AdaptedCursor:
        return _AdaptedCursor(self._conn.cursor())

    def commit(self): self._conn.commit()
    def rollback(self): self._conn.rollback()
    def execute(self, sql: str, params=None): return self.cursor().execute(sql, params)
    
    # IMPORTANTE: No implementamos .close() aquí para evitar que los repositorios maten la conexión física del pool
    def close(self): 
        # Si un repo llama a .close(), lo redirigimos a devolver al pool si es posible,
        # pero es preferible usar release_connection() explícito.
        release_connection(self)

# ---------------------------------------------------------------------------
# Gestión de Pool
# ---------------------------------------------------------------------------

def get_connection() -> _ConnectionWrapper:
    """Obtiene una conexión del pool global."""
    global _pool
    if _pool is None:
        # Fallback de seguridad (lazy init si no se llamó en main.py)
        init_db_pool()
    
    try:
        conn = _pool.getconn()
        # Aseguramos autocommit False para control de transacciones en repos
        conn.autocommit = False
        return _ConnectionWrapper(conn)
    except Exception:
        logger.exception("No se pudo obtener una conexión del pool")
        raise

def release_connection(wrapper: _ConnectionWrapper):
    """Devuelve la conexión al pool."""
    global _pool
    if _pool and wrapper and hasattr(wrapper, "_conn"):
        try:
            _pool.putconn(wrapper._conn)
        except Exception:
            logger.error("Error al devolver conexión al pool")

def reset_pg_connection():
    """Alias para compatibilidad con código antiguo que intentaba limpiar el thread-local."""
    pass
