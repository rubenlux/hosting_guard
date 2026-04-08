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


def release_connection() -> None:
    """
    Cierra la conexión del hilo actual y limpia el thread-local.

    Usar en background tasks (schedulers) para garantizar que cada ciclo
    comienza con una conexión fresca — evita OperationalError por
    conexiones PostgreSQL cerradas por el servidor tras idle prolongado.

    Safe to call even if no connection exists.
    """
    if BACKEND == "postgresql":
        reset_pg_connection()
        return

    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None


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

    CREATE TABLE IF NOT EXISTS site_health_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        site_id INTEGER NOT NULL,
        score INTEGER NOT NULL,
        status TEXT NOT NULL,
        cpu REAL NOT NULL,
        ram REAL NOT NULL,
        error_count INTEGER DEFAULT 0,
        warning_count INTEGER DEFAULT 0,
        alert_type TEXT,
        alert_message TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (site_id) REFERENCES hostings (hosting_id)
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

    CREATE TABLE IF NOT EXISTS site_health_history (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        site_id INTEGER NOT NULL,
        score INTEGER NOT NULL,
        status TEXT NOT NULL,
        cpu REAL NOT NULL,
        ram REAL NOT NULL,
        error_count INTEGER DEFAULT 0,
        warning_count INTEGER DEFAULT 0,
        alert_type TEXT,
        alert_message TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (site_id) REFERENCES hostings (hosting_id)
    );
"""

# Migraciones idempotentes: columnas añadidas después de la creación inicial
_MIGRATIONS_SQLITE = [
    """CREATE TABLE IF NOT EXISTS staff_accounts (
        staff_id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        last_login_at TEXT,
        FOREIGN KEY (admin_id) REFERENCES users (user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS staff_activity_log (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        staff_id INTEGER NOT NULL,
        action_type TEXT NOT NULL,
        target_user_id INTEGER,
        target_hosting_id INTEGER,
        description TEXT NOT NULL,
        duration_seconds INTEGER,
        ip_address TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (staff_id) REFERENCES staff_accounts (staff_id)
    )""",
    """CREATE TABLE IF NOT EXISTS support_sessions (
        session_id TEXT PRIMARY KEY,
        admin_id INTEGER NOT NULL,
        target_user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        revoked_at TEXT,
        ip_address TEXT,
        FOREIGN KEY (admin_id) REFERENCES users (user_id),
        FOREIGN KEY (target_user_id) REFERENCES users (user_id)
    )""",
    "ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0.0",
    "ALTER TABLE users ADD COLUMN has_payment_method INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN autoscale_enabled INTEGER DEFAULT 1",
    "ALTER TABLE users ADD COLUMN plan TEXT DEFAULT 'free'",
    "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'",
    "ALTER TABLE hostings ADD COLUMN ip_address TEXT",
    # ── Support session audit columns (v2) ───────────────────────────────────
    "ALTER TABLE support_sessions ADD COLUMN issue_description TEXT",
    "ALTER TABLE support_sessions ADD COLUMN origin TEXT DEFAULT 'manual'",
    "ALTER TABLE support_sessions ADD COLUMN session_type TEXT DEFAULT 'write'",
    "ALTER TABLE support_sessions ADD COLUMN initiated_by TEXT DEFAULT 'admin'",
    "ALTER TABLE support_sessions ADD COLUMN ended_at TEXT",
    "ALTER TABLE support_sessions ADD COLUMN result TEXT",
    "ALTER TABLE support_sessions ADD COLUMN resolution_notes TEXT",
    "ALTER TABLE support_sessions ADD COLUMN action_taken TEXT",
    "ALTER TABLE support_sessions ADD COLUMN staff_agent TEXT",
    "ALTER TABLE staff_activity_log ADD COLUMN session_id TEXT",
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
    # ── Support Chat tables (v3) ─────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS ticket_categories (
        category_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        ai_prompt_hint TEXT,
        priority_default TEXT NOT NULL DEFAULT 'medium',
        is_active INTEGER NOT NULL DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS support_tickets (
        ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        hosting_id INTEGER,
        category TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        priority TEXT NOT NULL DEFAULT 'medium',
        title TEXT NOT NULL,
        ai_summary TEXT,
        assigned_to INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        resolved_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS ticket_messages (
        message_id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id INTEGER NOT NULL,
        sender_type TEXT NOT NULL,
        sender_id INTEGER,
        content TEXT NOT NULL,
        metadata TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (ticket_id) REFERENCES support_tickets (ticket_id)
    )""",
    """CREATE TABLE IF NOT EXISTS support_chat_cache (
        cache_id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,
        sub_intent TEXT NOT NULL,
        problem_summary TEXT NOT NULL,
        ai_response TEXT NOT NULL,
        score INTEGER NOT NULL DEFAULT 50,
        uses INTEGER NOT NULL DEFAULT 0,
        resolutions INTEGER NOT NULL DEFAULT 0,
        hosting_id INTEGER,
        hosting_status_when_cached TEXT,
        hosting_updated_at_when_cached TEXT,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )""",
    # Seed de categorías iniciales (INSERT OR IGNORE = idempotente en SQLite)
    "INSERT OR IGNORE INTO ticket_categories (category_id, name, description, ai_prompt_hint, priority_default, is_active) VALUES (1, 'Sitio caído', 'El sitio web no responde o da error 502/503', 'El cliente reporta que su sitio web está completamente caído o inaccesible. Revisa el estado del contenedor Docker y los logs de nginx.', 'high', 1)",
    "INSERT OR IGNORE INTO ticket_categories (category_id, name, description, ai_prompt_hint, priority_default, is_active) VALUES (2, 'Sitio lento', 'El sitio carga muy despacio', 'El cliente reporta lentitud en su sitio web. Revisa CPU, memoria y conexiones activas del contenedor.', 'medium', 1)",
    "INSERT OR IGNORE INTO ticket_categories (category_id, name, description, ai_prompt_hint, priority_default, is_active) VALUES (3, 'Error en WordPress', 'Error 500, pantalla blanca o plugin roto en WordPress', 'El cliente tiene un sitio WordPress con errores. Puede ser un plugin incompatible, límite de memoria PHP o base de datos corrupta.', 'medium', 1)",
    "INSERT OR IGNORE INTO ticket_categories (category_id, name, description, ai_prompt_hint, priority_default, is_active) VALUES (4, 'Problema de billing', 'Cobros incorrectos, saldo o facturación', 'El cliente tiene una consulta sobre su factura, saldo o método de pago. Revisar el historial de transacciones.', 'low', 1)",
    "INSERT OR IGNORE INTO ticket_categories (category_id, name, description, ai_prompt_hint, priority_default, is_active) VALUES (5, 'Ayuda técnica', 'Configuración, DNS, SSL u otro problema técnico', 'El cliente necesita ayuda técnica general. Puede ser configuración de DNS, certificado SSL, redirecciones o deploy.', 'medium', 1)",
    "INSERT OR IGNORE INTO ticket_categories (category_id, name, description, ai_prompt_hint, priority_default, is_active) VALUES (6, 'Otro', 'Otro tipo de problema no clasificado', 'El cliente tiene una consulta general. Intentar clasificar el problema antes de responder.', 'low', 1)",
    # ── Orchestrator observability columns (v4) ───────────────────────────────────
    "ALTER TABLE orchestrator_events ADD COLUMN cpu_pct REAL",
    "ALTER TABLE orchestrator_events ADD COLUMN mem_pct REAL",
    "ALTER TABLE orchestrator_events ADD COLUMN risk_level TEXT",
    "ALTER TABLE orchestrator_events ADD COLUMN simulated INTEGER DEFAULT 1",
    """CREATE TABLE IF NOT EXISTS site_health_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        site_id INTEGER NOT NULL,
        score INTEGER NOT NULL,
        status TEXT NOT NULL,
        cpu REAL NOT NULL,
        ram REAL NOT NULL,
        error_count INTEGER DEFAULT 0,
        warning_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (site_id) REFERENCES hostings (hosting_id)
    )""",
]

_MIGRATIONS_PG = [
    """CREATE TABLE IF NOT EXISTS staff_accounts (
        staff_id SERIAL PRIMARY KEY,
        admin_id INTEGER NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        last_login_at TEXT,
        FOREIGN KEY (admin_id) REFERENCES users (user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS staff_activity_log (
        log_id SERIAL PRIMARY KEY,
        staff_id INTEGER NOT NULL,
        action_type TEXT NOT NULL,
        target_user_id INTEGER,
        target_hosting_id INTEGER,
        description TEXT NOT NULL,
        duration_seconds INTEGER,
        ip_address TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (staff_id) REFERENCES staff_accounts (staff_id)
    )""",
    """CREATE TABLE IF NOT EXISTS support_sessions (
        session_id TEXT PRIMARY KEY,
        admin_id INTEGER NOT NULL,
        target_user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        revoked_at TEXT,
        ip_address TEXT,
        FOREIGN KEY (admin_id) REFERENCES users (user_id),
        FOREIGN KEY (target_user_id) REFERENCES users (user_id)
    )""",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS balance REAL DEFAULT 0.0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS has_payment_method INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS autoscale_enabled INTEGER DEFAULT 1",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'free'",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'user'",
    "ALTER TABLE hostings ADD COLUMN IF NOT EXISTS ip_address TEXT",
    # ── Support session audit columns (v2) ───────────────────────────────────
    "ALTER TABLE support_sessions ADD COLUMN IF NOT EXISTS issue_description TEXT",
    "ALTER TABLE support_sessions ADD COLUMN IF NOT EXISTS origin TEXT DEFAULT 'manual'",
    "ALTER TABLE support_sessions ADD COLUMN IF NOT EXISTS session_type TEXT DEFAULT 'write'",
    "ALTER TABLE support_sessions ADD COLUMN IF NOT EXISTS initiated_by TEXT DEFAULT 'admin'",
    "ALTER TABLE support_sessions ADD COLUMN IF NOT EXISTS ended_at TEXT",
    "ALTER TABLE support_sessions ADD COLUMN IF NOT EXISTS result TEXT",
    "ALTER TABLE support_sessions ADD COLUMN IF NOT EXISTS resolution_notes TEXT",
    "ALTER TABLE support_sessions ADD COLUMN IF NOT EXISTS action_taken TEXT",
    "ALTER TABLE support_sessions ADD COLUMN IF NOT EXISTS staff_agent TEXT",
    "ALTER TABLE staff_activity_log ADD COLUMN IF NOT EXISTS session_id TEXT",
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
    # ── Support Chat tables (v3) ─────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS ticket_categories (
        category_id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        ai_prompt_hint TEXT,
        priority_default TEXT NOT NULL DEFAULT 'medium',
        is_active INTEGER NOT NULL DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS support_tickets (
        ticket_id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        hosting_id INTEGER,
        category TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        priority TEXT NOT NULL DEFAULT 'medium',
        title TEXT NOT NULL,
        ai_summary TEXT,
        assigned_to INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        resolved_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS ticket_messages (
        message_id SERIAL PRIMARY KEY,
        ticket_id INTEGER NOT NULL,
        sender_type TEXT NOT NULL,
        sender_id INTEGER,
        content TEXT NOT NULL,
        metadata TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (ticket_id) REFERENCES support_tickets (ticket_id)
    )""",
    """CREATE TABLE IF NOT EXISTS support_chat_cache (
        cache_id SERIAL PRIMARY KEY,
        category TEXT NOT NULL,
        sub_intent TEXT NOT NULL,
        problem_summary TEXT NOT NULL,
        ai_response TEXT NOT NULL,
        score INTEGER NOT NULL DEFAULT 50,
        uses INTEGER NOT NULL DEFAULT 0,
        resolutions INTEGER NOT NULL DEFAULT 0,
        hosting_id INTEGER,
        hosting_status_when_cached TEXT,
        hosting_updated_at_when_cached TEXT,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )""",
    # Seed de categorías iniciales (ON CONFLICT DO NOTHING = idempotente en PostgreSQL)
    "INSERT INTO ticket_categories (category_id, name, description, ai_prompt_hint, priority_default, is_active) VALUES (1, 'Sitio caído', 'El sitio web no responde o da error 502/503', 'El cliente reporta que su sitio web está completamente caído o inaccesible. Revisa el estado del contenedor Docker y los logs de nginx.', 'high', 1) ON CONFLICT (category_id) DO NOTHING",
    "INSERT INTO ticket_categories (category_id, name, description, ai_prompt_hint, priority_default, is_active) VALUES (2, 'Sitio lento', 'El sitio carga muy despacio', 'El cliente reporta lentitud en su sitio web. Revisa CPU, memoria y conexiones activas del contenedor.', 'medium', 1) ON CONFLICT (category_id) DO NOTHING",
    "INSERT INTO ticket_categories (category_id, name, description, ai_prompt_hint, priority_default, is_active) VALUES (3, 'Error en WordPress', 'Error 500, pantalla blanca o plugin roto en WordPress', 'El cliente tiene un sitio WordPress con errores. Puede ser un plugin incompatible, límite de memoria PHP o base de datos corrupta.', 'medium', 1) ON CONFLICT (category_id) DO NOTHING",
    "INSERT INTO ticket_categories (category_id, name, description, ai_prompt_hint, priority_default, is_active) VALUES (4, 'Problema de billing', 'Cobros incorrectos, saldo o facturación', 'El cliente tiene una consulta sobre su factura, saldo o método de pago. Revisar el historial de transacciones.', 'low', 1) ON CONFLICT (category_id) DO NOTHING",
    "INSERT INTO ticket_categories (category_id, name, description, ai_prompt_hint, priority_default, is_active) VALUES (5, 'Ayuda técnica', 'Configuración, DNS, SSL u otro problema técnico', 'El cliente necesita ayuda técnica general. Puede ser configuración de DNS, certificado SSL, redirecciones o deploy.', 'medium', 1) ON CONFLICT (category_id) DO NOTHING",
    "INSERT INTO ticket_categories (category_id, name, description, ai_prompt_hint, priority_default, is_active) VALUES (6, 'Otro', 'Otro tipo de problema no clasificado', 'El cliente tiene una consulta general. Intentar clasificar el problema antes de responder.', 'low', 1) ON CONFLICT (category_id) DO NOTHING",
    # ── Orchestrator observability columns (v4) ───────────────────────────────────
    "ALTER TABLE orchestrator_events ADD COLUMN IF NOT EXISTS cpu_pct REAL",
    "ALTER TABLE orchestrator_events ADD COLUMN IF NOT EXISTS mem_pct REAL",
    "ALTER TABLE orchestrator_events ADD COLUMN IF NOT EXISTS risk_level TEXT",
    "ALTER TABLE orchestrator_events ADD COLUMN IF NOT EXISTS simulated INTEGER DEFAULT 1",
    """CREATE TABLE IF NOT EXISTS site_health_history (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        site_id INTEGER NOT NULL,
        score INTEGER NOT NULL,
        status TEXT NOT NULL,
        cpu REAL NOT NULL,
        ram REAL NOT NULL,
        error_count INTEGER DEFAULT 0,
        warning_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (site_id) REFERENCES hostings (hosting_id)
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
    # Support Chat indexes
    "CREATE INDEX IF NOT EXISTS idx_tickets_user ON support_tickets(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_tickets_status ON support_tickets(status)",
    "CREATE INDEX IF NOT EXISTS idx_tickets_assigned ON support_tickets(assigned_to)",
    "CREATE INDEX IF NOT EXISTS idx_messages_ticket ON ticket_messages(ticket_id)",
    "CREATE INDEX IF NOT EXISTS idx_support_cache_lookup ON support_chat_cache(category, sub_intent)",
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

    # Invalidar cache técnico al deploy (startup)
    cursor.execute("DELETE FROM support_chat_cache WHERE category IN ('Sitio caído', 'Sitio lento', 'Error en WordPress')")

    conn.commit()
    # Cerrar la conexión de init y limpiar el pool para que la primera
    # solicitud real obtenga una conexión limpia con WAL ya activado.
    conn.close()
    _local.conn = None


def _init_postgresql_audit():
    conn = get_pg_connection()
    cursor = conn.cursor()
    try:
        for statement in _SCHEMA_AUDIT_PG.strip().split(";"):
            sql = statement.strip()
            if sql:
                cursor.execute(sql)

        for sql in _MIGRATIONS_PG:
            cursor.execute(sql)

        for sql in _INDEXES:
            cursor.execute(sql)

        # Invalidar cache técnico al deploy (startup)
        cursor.execute("DELETE FROM support_chat_cache WHERE category IN ('Sitio caído', 'Sitio lento', 'Error en WordPress')")

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        reset_pg_connection()
