import logging
from app.infra.db import get_connection

logger = logging.getLogger(__name__)

# Esquema base de Auditoría y Sistema
_SCHEMA_PG = """
    CREATE TABLE IF NOT EXISTS users (
        user_id SERIAL PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        balance REAL DEFAULT 0.0,
        has_payment_method INTEGER DEFAULT 0,
        autoscale_enabled INTEGER DEFAULT 1,
        plan TEXT DEFAULT 'free',
        role TEXT DEFAULT 'user',
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
        cpu_pct REAL,
        mem_pct REAL,
        risk_level TEXT,
        simulated INTEGER DEFAULT 1,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    );

    CREATE TABLE IF NOT EXISTS tenant_configs (
        config_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        kind TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL,
        active INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS pixel_sites (
        site_id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        domain TEXT,
        created_at TIMESTAMPTZ NOT NULL,
        last_seen_at TIMESTAMPTZ
    );

    CREATE TABLE IF NOT EXISTS pixel_events (
        event_id TEXT,
        site_id TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        url TEXT,
        referrer TEXT,
        user_agent TEXT,
        ip TEXT,
        country TEXT,
        device TEXT,
        browser TEXT,
        os TEXT,
        properties JSONB,
        session_id TEXT,
        visitor_id TEXT,
        region TEXT,
        city TEXT,
        created_at TIMESTAMPTZ NOT NULL
    ) PARTITION BY RANGE (created_at);
"""

# Migraciones incrementales y Tablas Adicionales
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
        session_id TEXT,
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
        issue_description TEXT,
        origin TEXT DEFAULT 'manual',
        session_type TEXT DEFAULT 'write',
        initiated_by TEXT DEFAULT 'admin',
        ended_at TEXT,
        result TEXT,
        resolution_notes TEXT,
        action_taken TEXT,
        staff_agent TEXT,
        FOREIGN KEY (admin_id) REFERENCES users (user_id),
        FOREIGN KEY (target_user_id) REFERENCES users (user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS traffic_stats (
        id SERIAL PRIMARY KEY,
        container_name TEXT NOT NULL,
        collected_at TEXT NOT NULL,
        total_requests INTEGER DEFAULT 0,
        errors_4xx INTEGER DEFAULT 0,
        errors_5xx INTEGER DEFAULT 0
    )""",
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
        alert_type TEXT,
        alert_message TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (site_id) REFERENCES hostings (hosting_id)
    )""",
    """CREATE TABLE IF NOT EXISTS site_alerts (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        site_id INTEGER NOT NULL,
        level TEXT NOT NULL,
        message TEXT NOT NULL,
        resolved INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (site_id) REFERENCES hostings (hosting_id)
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
    """CREATE TABLE IF NOT EXISTS ticket_categories (
        category_id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        ai_prompt_hint TEXT,
        priority_default TEXT NOT NULL DEFAULT 'medium',
        is_active INTEGER NOT NULL DEFAULT 1
    )""",
    "INSERT INTO ticket_categories (category_id, name, description, ai_prompt_hint, priority_default, is_active) VALUES (1, 'Sitio caído', 'El sitio web no responde o da error 502/503', '...', 'high', 1) ON CONFLICT (category_id) DO NOTHING",
    "INSERT INTO ticket_categories (category_id, name, description, ai_prompt_hint, priority_default, is_active) VALUES (2, 'Sitio lento', 'El sitio carga muy despacio', '...', 'medium', 1) ON CONFLICT (category_id) DO NOTHING",
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_login_audit_email ON login_audit(email)",
    "CREATE INDEX IF NOT EXISTS idx_hostings_container ON hostings(container_name)",
    "CREATE INDEX IF NOT EXISTS idx_tickets_user ON support_tickets(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_pixel_events_site_created ON pixel_events (site_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_pixel_events_site_type_created ON pixel_events (site_id, event_type, created_at)",
    # Covers bounce rate subquery: WHERE site_id=? AND session_id IS NOT NULL AND created_at>=? GROUP BY session_id
    "CREATE INDEX IF NOT EXISTS idx_pixel_events_site_session_created ON pixel_events (site_id, session_id, created_at)",
    # Covers COUNT(DISTINCT COALESCE(visitor_id, session_id)) in realtime + active_users_5min queries
    "CREATE INDEX IF NOT EXISTS idx_pixel_events_site_visitor_created ON pixel_events (site_id, visitor_id, created_at)",
    # Covers top-pages query: WHERE site_id=? AND event_type='page_view' AND created_at>=? GROUP BY url
    "CREATE INDEX IF NOT EXISTS idx_pixel_events_pages ON pixel_events (site_id, event_type, created_at, url)",
    # Covers device breakdown: WHERE site_id=? AND device IS NOT NULL AND created_at>=? GROUP BY device
    "CREATE INDEX IF NOT EXISTS idx_pixel_events_device ON pixel_events (site_id, device, created_at)",
    # Covers country breakdown: WHERE site_id=? AND country IS NOT NULL AND created_at>=? GROUP BY country
    "CREATE INDEX IF NOT EXISTS idx_pixel_events_country ON pixel_events (site_id, country, created_at)",
]

def ensure_monthly_partitions(cursor):
    """Garantiza que existan particiones para el mes actual y los próximos 2 meses.

    Si pixel_events no es una tabla particionada (p.ej. fue creada antes de la
    migración a particiones), omite silenciosamente el mantenimiento.
    """
    from datetime import datetime, timedelta, timezone

    # Verificar si pixel_events es realmente una tabla particionada.
    # RealDictCursor devuelve dicts, no tuplas — usamos alias explícito.
    cursor.execute("""
        SELECT COUNT(*) AS cnt FROM pg_partitioned_table pt
        JOIN pg_class c ON c.oid = pt.partrelid
        WHERE c.relname = 'pixel_events'
    """)
    row = cursor.fetchone()
    if not row or row["cnt"] == 0:
        logger.debug("pixel_events is not a partitioned table — skipping partition maintenance")
        return

    now = datetime.now(timezone.utc)

    for delta in [0, 1, 2]:
        # Calcular primer día del mes objetivo
        target_month = now.month + delta
        target_year = now.year + (target_month - 1) // 12
        target_month = (target_month - 1) % 12 + 1
        
        start_date = datetime(target_year, target_month, 1, tzinfo=timezone.utc)
        
        # Calcular primer día del mes siguiente
        next_month = target_month + 1
        next_year = target_year + (next_month - 1) // 12
        next_month = (next_month - 1) % 12 + 1
        end_date = datetime(next_year, next_month, 1, tzinfo=timezone.utc)

        suffix = start_date.strftime("%Y_%m")
        table_name = f"pixel_events_{suffix}"

        # Usar parámetros para evitar inyección y errores de formato
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} 
            PARTITION OF pixel_events 
            FOR VALUES FROM (%s) TO (%s)
        """, (start_date, end_date))
    
    # Crear partición default para evitar fallos de inserción
    cursor.execute("CREATE TABLE IF NOT EXISTS pixel_events_default PARTITION OF pixel_events DEFAULT")

def init_db():
    """Inicialización idempotente de PostgreSQL."""
    from app.infra.db import release_connection
    conn = None
    try:
        conn = get_connection()
        conn._conn.autocommit = True
        cursor = conn.cursor()
        
        # 1. Esquema base
        for statement in _SCHEMA_PG.strip().split(";"):
            sql = statement.strip()
            if sql:
                try:
                    cursor.execute(sql)
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        logger.warning(f"Schema item error: {e}")

        # 2. Migraciones
        for sql in _MIGRATIONS_PG:
            try:
                cursor.execute(sql)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.warning(f"Migration error: {e}")

        # 3. Particiones de Analytics (Capa Temporal)
        try:
            ensure_monthly_partitions(cursor)
        except Exception as e:
            logger.warning(f"Partition maintenance error: {e}")

        # 4. Índices
        for sql in _INDEXES:
            try:
                cursor.execute(sql)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.warning(f"Index error: {e}")

        logger.info("Database (PostgreSQL) Initialized with Partitions.")
    except Exception as e:
        logger.error(f"FAIL: init_db (Postgres) failed: {e}", exc_info=True)
    finally:
        if conn is not None:
            conn._conn.autocommit = False
            release_connection(conn)
