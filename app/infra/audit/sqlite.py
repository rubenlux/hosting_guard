import os
import sqlite3
import threading
from pathlib import Path

from app.infra.db import BACKEND, _ConnectionAdapter, get_pg_connection, reset_pg_connection

# ---------------------------------------------------------------------------
# SQLite pool thread-local (solo se usa cuando BACKEND == "sqlite")
# ---------------------------------------------------------------------------

DB_PATH = Path(os.getenv("AUDIT_DB_PATH", "audit_events.sqlite"))

_local = threading.local()


def get_connection() -> _ConnectionAdapter:
    """
    Devuelve la conexión del hilo actual envuelta en _ConnectionAdapter.

    - SQLite  → pool thread-local con WAL + busy_timeout.
    - PostgreSQL → pool thread-local gestionado por app.infra.db.
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


# ---------------------------------------------------------------------------
# Esquemas
# ---------------------------------------------------------------------------

_SCHEMA_AUDIT_SQLITE = """
    CREATE TABLE IF NOT EXISTS decision_events (
        event_id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        decision_id TEXT NOT NULL,
        overall_status TEXT NOT NULL,
        confidence_level TEXT NOT NULL,
        requires_human_attention INTEGER NOT NULL,
        payload_min TEXT NOT NULL,
        version INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS human_action_events (
        action_event_id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        decision_id TEXT NOT NULL,
        action_type TEXT NOT NULL,
        actor TEXT NOT NULL,
        reason TEXT,
        version INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS execution_events (
        execution_id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        decision_id TEXT NOT NULL,
        action_type TEXT NOT NULL,
        status TEXT NOT NULL,
        version INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        balance REAL DEFAULT 0.0,
        has_payment_method INTEGER DEFAULT 0,
        autoscale_enabled INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS login_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        ip TEXT NOT NULL,
        success INTEGER NOT NULL,
        detail TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS hostings (
        hosting_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        subdomain TEXT NOT NULL UNIQUE,
        container_name TEXT NOT NULL UNIQUE,
        plan TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        ip_address TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    );

    CREATE TABLE IF NOT EXISTS orchestrator_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        container_name TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    );
"""

_SCHEMA_AUDIT_PG = """
    CREATE TABLE IF NOT EXISTS decision_events (
        event_id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        decision_id TEXT NOT NULL,
        overall_status TEXT NOT NULL,
        confidence_level TEXT NOT NULL,
        requires_human_attention INTEGER NOT NULL,
        payload_min TEXT NOT NULL,
        version INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS human_action_events (
        action_event_id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        decision_id TEXT NOT NULL,
        action_type TEXT NOT NULL,
        actor TEXT NOT NULL,
        reason TEXT,
        version INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS execution_events (
        execution_id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        decision_id TEXT NOT NULL,
        action_type TEXT NOT NULL,
        status TEXT NOT NULL,
        version INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS users (
        user_id SERIAL PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        balance REAL DEFAULT 0.0,
        has_payment_method INTEGER DEFAULT 0,
        autoscale_enabled INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS login_audit (
        id SERIAL PRIMARY KEY,
        email TEXT NOT NULL,
        ip TEXT NOT NULL,
        success INTEGER NOT NULL,
        detail TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS hostings (
        hosting_id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        subdomain TEXT NOT NULL UNIQUE,
        container_name TEXT NOT NULL UNIQUE,
        plan TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        ip_address TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    );

    CREATE TABLE IF NOT EXISTS orchestrator_events (
        event_id SERIAL PRIMARY KEY,
        container_name TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    );
"""

# Migraciones idempotentes: columnas añadidas después de la creación inicial
_MIGRATIONS_SQLITE = [
    "ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0.0",
    "ALTER TABLE users ADD COLUMN has_payment_method INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN autoscale_enabled INTEGER DEFAULT 1",
    "ALTER TABLE users ADD COLUMN plan TEXT DEFAULT 'free'",
    "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'",
    "ALTER TABLE hostings ADD COLUMN ip_address TEXT",
    """CREATE TABLE IF NOT EXISTS traffic_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        container_name TEXT NOT NULL,
        collected_at TEXT NOT NULL,
        total_requests INTEGER DEFAULT 0,
        errors_4xx INTEGER DEFAULT 0,
        errors_5xx INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS uptime_checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hosting_id INTEGER NOT NULL,
        checked_at TEXT NOT NULL,
        is_up INTEGER NOT NULL,
        response_ms INTEGER,
        status_code INTEGER
    )""",
]

_MIGRATIONS_PG = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS balance REAL DEFAULT 0.0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS has_payment_method INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS autoscale_enabled INTEGER DEFAULT 1",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'free'",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'user'",
    "ALTER TABLE hostings ADD COLUMN IF NOT EXISTS ip_address TEXT",
    """CREATE TABLE IF NOT EXISTS traffic_stats (
        id SERIAL PRIMARY KEY,
        container_name TEXT NOT NULL,
        collected_at TEXT NOT NULL,
        total_requests INTEGER DEFAULT 0,
        errors_4xx INTEGER DEFAULT 0,
        errors_5xx INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS uptime_checks (
        id SERIAL PRIMARY KEY,
        hosting_id INTEGER NOT NULL,
        checked_at TEXT NOT NULL,
        is_up INTEGER NOT NULL,
        response_ms INTEGER,
        status_code INTEGER
    )""",
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_login_audit_email ON login_audit(email)",
    "CREATE INDEX IF NOT EXISTS idx_hostings_container ON hostings(container_name)",
    "CREATE INDEX IF NOT EXISTS idx_hostings_user ON hostings(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_hostings_ip ON hostings(ip_address)",
    "CREATE INDEX IF NOT EXISTS idx_traffic_container ON traffic_stats(container_name)",
    "CREATE INDEX IF NOT EXISTS idx_traffic_collected ON traffic_stats(collected_at)",
    "CREATE INDEX IF NOT EXISTS idx_uptime_hosting ON uptime_checks(hosting_id)",
    "CREATE INDEX IF NOT EXISTS idx_uptime_checked ON uptime_checks(checked_at)",
]


def init_db():
    if BACKEND == "postgresql":
        _init_postgresql_audit()
    else:
        _init_sqlite_audit()


def _init_sqlite_audit():
    conn = get_connection()
    cursor = conn.cursor()

    for statement in _SCHEMA_AUDIT_SQLITE.strip().split(";"):
        sql = statement.strip()
        if sql:
            cursor.execute(sql)

    for sql in _MIGRATIONS_SQLITE:
        try:
            cursor.execute(sql)
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                raise

    for sql in _INDEXES:
        cursor.execute(sql)

    conn.commit()
    # Cerrar la conexión de init y limpiar el pool para que la primera
    # solicitud real obtenga una conexión limpia con WAL ya activado.
    conn.close()
    _local.conn = None


def _init_postgresql_audit():
    conn = get_pg_connection()
    cursor = conn.cursor()

    for statement in _SCHEMA_AUDIT_PG.strip().split(";"):
        sql = statement.strip()
        if sql:
            cursor.execute(sql)

    for sql in _MIGRATIONS_PG:
        cursor.execute(sql)

    for sql in _INDEXES:
        cursor.execute(sql)

    conn.commit()
    reset_pg_connection()
