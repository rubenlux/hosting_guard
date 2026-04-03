import os
import sqlite3
import threading
from pathlib import Path

from app.infra.db import BACKEND, _ConnectionAdapter, get_pg_connection, reset_pg_connection

# ---------------------------------------------------------------------------
# SQLite pool thread-local (solo se usa cuando BACKEND == "sqlite")
# ---------------------------------------------------------------------------

DB_PATH = Path(os.getenv("CONFIG_DB_PATH", "/app/data/tenant_configs.sqlite"))

# Asegurar que la carpeta exista (solo relevante para SQLite)
if BACKEND == "sqlite":
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_local = threading.local()


def get_connection() -> _ConnectionAdapter:
    """
    Devuelve la conexión del hilo actual envuelta en _ConnectionAdapter.

    - SQLite      → pool thread-local con WAL + busy_timeout.
    - PostgreSQL  → pool thread-local gestionado por app.infra.db.
    """
    if BACKEND == "postgresql":
        return get_pg_connection()

    conn = getattr(_local, "conn", None)
    if conn is None:
        raw = sqlite3.connect(DB_PATH, check_same_thread=False)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA journal_mode=WAL")
        raw.execute("PRAGMA busy_timeout=5000")
        conn = _ConnectionAdapter(raw, "sqlite")
        _local.conn = conn
    return conn


def init_db():
    if BACKEND == "postgresql":
        _init_postgresql_config()
    else:
        _init_sqlite_config()


def _init_sqlite_config():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_configs (
            config_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            kind TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            active INTEGER NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()
    _local.conn = None


def _init_postgresql_config():
    conn = get_pg_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_configs (
            config_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            kind TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            active INTEGER NOT NULL
        )
        """
    )

    conn.commit()
    reset_pg_connection()
