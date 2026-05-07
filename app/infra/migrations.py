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
        created_at TIMESTAMPTZ NOT NULL,
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
    # Phase 2: store db container name explicitly — avoids fragile dynamic name reconstruction
    "ALTER TABLE hostings ADD COLUMN IF NOT EXISTS db_container_name TEXT",
    # resolved_at timestamp for site_alerts — enables proper resolution tracking
    # (previously only 'resolved' INTEGER existed; frontend needs resolved_at)
    "ALTER TABLE site_alerts ADD COLUMN IF NOT EXISTS resolved_at TEXT",
    # fingerprint column for cache lookups (added after initial table creation)
    "ALTER TABLE ai_diagnosis ADD COLUMN IF NOT EXISTS fingerprint TEXT",
    # failure_type classification (syntax | import | runtime | infra | unknown)
    "ALTER TABLE ai_diagnosis ADD COLUMN IF NOT EXISTS failure_type TEXT",
    # AI Diagnosis history — structured LLM output, append-only
    """CREATE TABLE IF NOT EXISTS ai_diagnosis (
        id           SERIAL PRIMARY KEY,
        hosting_id   INTEGER NOT NULL,
        user_id      INTEGER NOT NULL,
        severity     TEXT,
        summary      TEXT,
        root_cause   TEXT,
        file_path    TEXT,
        line_number  TEXT,
        service      TEXT,
        evidence     TEXT,
        impact       TEXT,
        fix_action   TEXT,
        fix_steps    TEXT,
        confidence   REAL,
        raw_response TEXT,
        created_at   TEXT NOT NULL,
        FOREIGN KEY (hosting_id) REFERENCES hostings (hosting_id)
    )""",
    # Convert orchestrator_events.created_at TEXT → TIMESTAMPTZ so time-range
    # queries use native comparison instead of lexicographic string ordering.
    """
    DO $$ BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'orchestrator_events'
          AND column_name = 'created_at'
          AND data_type = 'text'
      ) THEN
        ALTER TABLE orchestrator_events
          ALTER COLUMN created_at TYPE TIMESTAMPTZ
          USING created_at::TIMESTAMPTZ;
      END IF;
    END $$
    """,
    """CREATE TABLE IF NOT EXISTS backups (
        backup_id SERIAL PRIMARY KEY,
        hosting_id INTEGER NOT NULL REFERENCES hostings(hosting_id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        site_name TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        db_path TEXT,
        files_path TEXT,
        size_bytes BIGINT DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'pending',
        error_message TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS ssl_checks (
        check_id SERIAL PRIMARY KEY,
        hosting_id INTEGER NOT NULL REFERENCES hostings(hosting_id) ON DELETE CASCADE,
        subdomain TEXT NOT NULL,
        checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        is_valid BOOLEAN,
        days_remaining INTEGER,
        expires_at TIMESTAMPTZ,
        error TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS uptime_checks (
        id SERIAL PRIMARY KEY,
        hosting_id INTEGER NOT NULL REFERENCES hostings(hosting_id) ON DELETE CASCADE,
        checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        is_up INTEGER NOT NULL DEFAULT 0,
        response_ms INTEGER,
        status_code INTEGER
    )""",
    "CREATE INDEX IF NOT EXISTS idx_uptime_checks_hosting_time ON uptime_checks(hosting_id, checked_at DESC)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_backup_codes TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS notification_prefs JSONB",
    # ── Lemon Squeezy billing (annual subscriptions) ────────────────────────
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS ls_customer_id TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS ls_subscription_id TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS ls_variant_id TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'none'",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS current_period_start TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS current_period_end TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_ends_at TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_started_at TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS billing_interval TEXT DEFAULT 'yearly'",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS ls_customer_portal_url TEXT",
    """CREATE TABLE IF NOT EXISTS ls_webhook_events (
        event_id     TEXT PRIMARY KEY,
        event_name   TEXT NOT NULL,
        processed_at TEXT NOT NULL
    )""",

    # ── User presence — heartbeat-updated session tracking ───────────────────
    """CREATE TABLE IF NOT EXISTS user_sessions (
        session_id   TEXT PRIMARY KEY,
        user_id      INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
        email        TEXT,
        ip           TEXT,
        user_agent   TEXT,
        current_path TEXT,
        last_seen    TIMESTAMPTZ DEFAULT NOW(),
        created_at   TIMESTAMPTZ DEFAULT NOW(),
        expires_at   TIMESTAMPTZ,
        is_active    BOOLEAN DEFAULT TRUE
    )""",

    # ── Activity / audit trail — unified event log ────────────────────────────
    """CREATE TABLE IF NOT EXISTS activity_events (
        event_id      BIGSERIAL PRIMARY KEY,
        user_id       INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
        hosting_id    INTEGER REFERENCES hostings(hosting_id) ON DELETE SET NULL,
        actor_type    TEXT NOT NULL DEFAULT 'user',
        actor_user_id INTEGER,
        actor_email   TEXT,
        event_type    TEXT NOT NULL,
        category      TEXT NOT NULL,
        severity      TEXT NOT NULL DEFAULT 'info',
        title         TEXT NOT NULL,
        message       TEXT,
        metadata      JSONB DEFAULT '{}',
        ip            TEXT,
        user_agent    TEXT,
        source        TEXT,
        created_at    TIMESTAMPTZ DEFAULT NOW()
    )""",

    # ── GitHub deploy: per-hosting build config + webhook token ─────────────────
    "ALTER TABLE hostings ADD COLUMN IF NOT EXISTS git_config JSONB",
    "ALTER TABLE hostings ADD COLUMN IF NOT EXISTS webhook_token TEXT",
    "ALTER TABLE hostings ADD COLUMN IF NOT EXISTS deploy_logs JSONB DEFAULT '[]'::jsonb",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_hostings_webhook_token ON hostings(webhook_token) WHERE webhook_token IS NOT NULL",

    # ── Custom domains — per-hosting domain management ───────────────────────────
    """CREATE TABLE IF NOT EXISTS custom_domains (
        domain_id           SERIAL PRIMARY KEY,
        user_id             INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        hosting_id          INTEGER NOT NULL REFERENCES hostings(hosting_id) ON DELETE CASCADE,
        domain              TEXT NOT NULL,
        domain_type         TEXT NOT NULL DEFAULT 'subdomain',
        verification_token  TEXT NOT NULL,
        dns_status          TEXT NOT NULL DEFAULT 'pending',
        ssl_status          TEXT NOT NULL DEFAULT 'pending',
        is_primary          INTEGER NOT NULL DEFAULT 0,
        redirect_to_primary INTEGER NOT NULL DEFAULT 0,
        created_at          TIMESTAMPTZ DEFAULT NOW(),
        verified_at         TIMESTAMPTZ,
        last_checked_at     TIMESTAMPTZ,
        error_message       TEXT,
        UNIQUE(domain)
    )""",
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
    # AI diagnosis lookups by hosting (recency)
    "CREATE INDEX IF NOT EXISTS idx_ai_diagnosis_hosting ON ai_diagnosis (hosting_id, created_at DESC)",
    # AI diagnosis cache lookup by fingerprint
    "CREATE INDEX IF NOT EXISTS idx_ai_diagnosis_fp ON ai_diagnosis (hosting_id, fingerprint)",
    # Hostings lookup by owner — powers every user-facing hosting list query
    "CREATE INDEX IF NOT EXISTS idx_hostings_user ON hostings(user_id)",
    # Orchestrator event history per user — powers dashboard event feed + pagination
    "CREATE INDEX IF NOT EXISTS idx_orchestrator_events_user_created ON orchestrator_events(user_id, created_at)",
    # Plan management: explicit expiry override for free-tier users
    # NULL = use default 14-day rule; far-future date = free forever; past date = force-expire
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_expires_at TEXT",
    # User profile fields added in registration flow v2
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT",
    # Email verification — DEFAULT 1 grandfathers existing users as verified
    # new registrations explicitly set 0 in create_user()
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified INTEGER DEFAULT 1",
    # Tokens for email verification and password reset (single-use, time-limited)
    """CREATE TABLE IF NOT EXISTS auth_tokens (
        token_id   TEXT PRIMARY KEY,
        user_id    INTEGER NOT NULL,
        token_type TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used_at    TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )""",
    # Topup idempotency — prevents double-charge on network retry
    # Client sends a stable UUID per payment attempt; server rejects duplicates
    """CREATE TABLE IF NOT EXISTS topup_idempotency (
        idempotency_key TEXT PRIMARY KEY,
        user_id         INTEGER NOT NULL,
        amount          REAL NOT NULL,
        created_at      TEXT NOT NULL
    )""",
    # Soft-delete timestamp — preserves audit trail while marking resources as cleaned up
    "ALTER TABLE hostings ADD COLUMN IF NOT EXISTS deleted_at TEXT",
    # System alert events — persisted by the Prometheus alert poller
    """CREATE TABLE IF NOT EXISTS system_alert_events (
        id          SERIAL PRIMARY KEY,
        alert_name  TEXT NOT NULL,
        severity    TEXT NOT NULL,
        component   TEXT NOT NULL,
        message     TEXT NOT NULL,
        labels      TEXT,
        fired_at    TEXT NOT NULL,
        resolved_at TEXT
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS uix_system_alert_active ON system_alert_events (alert_name, (resolved_at IS NULL)) WHERE resolved_at IS NULL",
    # WordPress backup import jobs — tracks pipeline state, logs, and domain info
    """CREATE TABLE IF NOT EXISTS import_jobs (
        job_id          SERIAL PRIMARY KEY,
        hosting_id      INTEGER NOT NULL REFERENCES hostings(hosting_id),
        user_id         INTEGER NOT NULL REFERENCES users(user_id),
        status          TEXT NOT NULL DEFAULT 'uploading',
        backup_type     TEXT,
        original_domain TEXT,
        new_domain      TEXT,
        logs            TEXT NOT NULL DEFAULT '',
        error           TEXT,
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_import_jobs_user ON import_jobs (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_import_jobs_hosting ON import_jobs (hosting_id)",

    # ── Performance indexes (audit 2025-04) ─────────────────────────────────
    # Covers queries filtered by user_id AND status (list, count_active, soft-delete checks)
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_hostings_user_status ON hostings(user_id, status)",
    # Covers orchestrator dashboard queries ordered by container + recency
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_orch_container_created ON orchestrator_events(container_name, created_at DESC)",

    # user_sessions indexes
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_user_sessions_last_seen ON user_sessions(last_seen DESC)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_user_sessions_active_last ON user_sessions(is_active, last_seen DESC)",

    # activity_events indexes
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_activity_user_created ON activity_events(user_id, created_at DESC)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_activity_hosting_created ON activity_events(hosting_id, created_at DESC)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_activity_category_created ON activity_events(category, created_at DESC)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_activity_event_type_created ON activity_events(event_type, created_at DESC)",

    # ── Row-Level Security (RLS) — defense-in-depth for user-scoped tables ──
    # These policies enforce that non-superuser DB roles can only access their
    # own rows. With the current postgres superuser connection, RLS is bypassed
    # by default. To fully activate: create an `app_user` role (see db.py).
    #
    # Policy logic:
    #   ALLOW if user_id matches app.current_user_id (set per-transaction)
    #   OR if app.is_admin = '1' (set by admin endpoints)
    #
    # set_user_context() in db.py sets these transaction-local settings.

    "ALTER TABLE hostings ENABLE ROW LEVEL SECURITY",
    """
    DO $$ BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'hostings' AND policyname = 'hostings_tenant_isolation'
      ) THEN
        CREATE POLICY hostings_tenant_isolation ON hostings
          FOR ALL
          USING (
            user_id = NULLIF(current_setting('app.current_user_id', TRUE), '')::INTEGER
            OR current_setting('app.is_admin', TRUE) = '1'
          )
          WITH CHECK (
            user_id = NULLIF(current_setting('app.current_user_id', TRUE), '')::INTEGER
            OR current_setting('app.is_admin', TRUE) = '1'
          );
      END IF;
    END $$
    """,

    "ALTER TABLE orchestrator_events ENABLE ROW LEVEL SECURITY",
    """
    DO $$ BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'orchestrator_events' AND policyname = 'orch_events_tenant_isolation'
      ) THEN
        CREATE POLICY orch_events_tenant_isolation ON orchestrator_events
          FOR ALL
          USING (
            user_id = NULLIF(current_setting('app.current_user_id', TRUE), '')::INTEGER
            OR current_setting('app.is_admin', TRUE) = '1'
          )
          WITH CHECK (
            user_id = NULLIF(current_setting('app.current_user_id', TRUE), '')::INTEGER
            OR current_setting('app.is_admin', TRUE) = '1'
          );
      END IF;
    END $$
    """,

    "ALTER TABLE site_health_history ENABLE ROW LEVEL SECURITY",
    """
    DO $$ BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'site_health_history' AND policyname = 'health_history_tenant_isolation'
      ) THEN
        CREATE POLICY health_history_tenant_isolation ON site_health_history
          FOR ALL
          USING (
            user_id = NULLIF(current_setting('app.current_user_id', TRUE), '')::INTEGER
            OR current_setting('app.is_admin', TRUE) = '1'
          )
          WITH CHECK (
            user_id = NULLIF(current_setting('app.current_user_id', TRUE), '')::INTEGER
            OR current_setting('app.is_admin', TRUE) = '1'
          );
      END IF;
    END $$
    """,

    "ALTER TABLE site_alerts ENABLE ROW LEVEL SECURITY",
    """
    DO $$ BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'site_alerts' AND policyname = 'site_alerts_tenant_isolation'
      ) THEN
        CREATE POLICY site_alerts_tenant_isolation ON site_alerts
          FOR ALL
          USING (
            user_id = NULLIF(current_setting('app.current_user_id', TRUE), '')::INTEGER
            OR current_setting('app.is_admin', TRUE) = '1'
          )
          WITH CHECK (
            user_id = NULLIF(current_setting('app.current_user_id', TRUE), '')::INTEGER
            OR current_setting('app.is_admin', TRUE) = '1'
          );
      END IF;
    END $$
    """,

    "ALTER TABLE import_jobs ENABLE ROW LEVEL SECURITY",
    """
    DO $$ BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'import_jobs' AND policyname = 'import_jobs_tenant_isolation'
      ) THEN
        CREATE POLICY import_jobs_tenant_isolation ON import_jobs
          FOR ALL
          USING (
            user_id = NULLIF(current_setting('app.current_user_id', TRUE), '')::INTEGER
            OR current_setting('app.is_admin', TRUE) = '1'
          )
          WITH CHECK (
            user_id = NULLIF(current_setting('app.current_user_id', TRUE), '')::INTEGER
            OR current_setting('app.is_admin', TRUE) = '1'
          );
      END IF;
    END $$
    """,
    # Add wp_admin_password to hostings for auto-provisioned WordPress credentials
    """
    DO $$ BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'hostings' AND column_name = 'wp_admin_password'
      ) THEN
        ALTER TABLE hostings ADD COLUMN wp_admin_password TEXT;
      END IF;
    END $$
    """,
    # User profile extended fields
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS company TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT",
    # Notification preferences stored as JSON (e.g. {"site_down": true, "payment": false})
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS notification_prefs TEXT",

    # ── Notifications system ─────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS notifications (
        notification_id SERIAL PRIMARY KEY,
        user_id         INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        title           TEXT NOT NULL,
        message         TEXT NOT NULL,
        category        TEXT NOT NULL,
        severity        TEXT NOT NULL DEFAULT 'info',
        channel         TEXT NOT NULL DEFAULT 'dashboard',
        status          TEXT NOT NULL DEFAULT 'unread',
        action_url      TEXT,
        metadata        JSONB,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        read_at         TIMESTAMPTZ
    )""",
    "CREATE INDEX IF NOT EXISTS idx_notifications_user_status ON notifications(user_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_notifications_user_created ON notifications(user_id, created_at DESC)",

    # ── Admin audit log ──────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS admin_audit_log (
        audit_id        SERIAL PRIMARY KEY,
        admin_id        INTEGER NOT NULL REFERENCES users(user_id),
        admin_email     TEXT NOT NULL,
        action          TEXT NOT NULL,
        target_user_id  INTEGER REFERENCES users(user_id),
        target_email    TEXT,
        ip              TEXT,
        user_agent      TEXT,
        details         TEXT,
        reason          TEXT,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_admin_audit_admin ON admin_audit_log(admin_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_admin_audit_target ON admin_audit_log(target_user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_backups_hosting ON backups(hosting_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_backups_user ON backups(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_ssl_checks_hosting ON ssl_checks(hosting_id, checked_at DESC)",
    # Allow user_id=NULL for system-level orchestrator events (expiration_job summary, traffic_collector)
    "ALTER TABLE orchestrator_events ALTER COLUMN user_id DROP NOT NULL",

    # ── Security events — attack detection + incident tracking ────────────────
    """CREATE TABLE IF NOT EXISTS security_events (
        event_id      BIGSERIAL PRIMARY KEY,
        user_id       INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
        hosting_id    INTEGER REFERENCES hostings(hosting_id) ON DELETE SET NULL,
        severity      TEXT NOT NULL,
        category      TEXT NOT NULL,
        event_type    TEXT NOT NULL,
        title         TEXT NOT NULL,
        message       TEXT,
        ip            TEXT,
        user_agent    TEXT,
        path          TEXT,
        source        TEXT,
        metadata      JSONB DEFAULT '{}',
        status        TEXT NOT NULL DEFAULT 'open',
        count         INTEGER NOT NULL DEFAULT 1,
        last_seen     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        resolved_at   TIMESTAMPTZ,
        resolved_by   INTEGER REFERENCES users(user_id) ON DELETE SET NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_sec_events_created   ON security_events(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sec_events_severity  ON security_events(severity, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sec_events_category  ON security_events(category, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sec_events_user      ON security_events(user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sec_events_hosting   ON security_events(hosting_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sec_events_status    ON security_events(status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sec_events_ip        ON security_events(ip, created_at DESC)",

    # protection_mode per hosting — stores WAF/rate-limit settings as JSONB
    "ALTER TABLE hostings ADD COLUMN IF NOT EXISTS protection_mode JSONB DEFAULT '{}'",

    # ── security_events back-compat: add columns that may be absent on existing tables ──
    # (CREATE TABLE IF NOT EXISTS is idempotent but doesn't add columns to pre-existing tables)
    "ALTER TABLE security_events ADD COLUMN IF NOT EXISTS count    INTEGER    NOT NULL DEFAULT 1",
    "ALTER TABLE security_events ADD COLUMN IF NOT EXISTS last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW()",
    # Backfill last_seen = created_at for rows that didn't have it yet
    """UPDATE security_events SET last_seen = created_at WHERE last_seen = NOW() AND created_at < NOW() - INTERVAL '5 seconds'""",

    # ── Hosting resource samples — written by collect_resource_usage job every 60s ──
    """CREATE TABLE IF NOT EXISTS hosting_resource_samples (
        sample_id      BIGSERIAL PRIMARY KEY,
        hosting_id     INTEGER NOT NULL REFERENCES hostings(hosting_id) ON DELETE CASCADE,
        container_name TEXT NOT NULL,
        cpu_pct        REAL,
        mem_mb         REAL,
        mem_limit_mb   REAL,
        net_rx_mb      REAL,
        net_tx_mb      REAL,
        sampled_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_resource_samples_hosting_time ON hosting_resource_samples(hosting_id, sampled_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_resource_samples_sampled_at ON hosting_resource_samples(sampled_at DESC)",
    # user_id added after initial deploy — lets admin queries filter/group by owner
    "ALTER TABLE hosting_resource_samples ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL",
    "CREATE INDEX IF NOT EXISTS idx_resource_samples_user_time ON hosting_resource_samples(user_id, sampled_at DESC)",
    "ALTER TABLE hosting_resource_samples ADD COLUMN IF NOT EXISTS disk_mb REAL",

    # ── Unit-economics: plan pricing catalog ──────────────────────────────────
    """CREATE TABLE IF NOT EXISTS plan_economics (
        plan_name                    TEXT PRIMARY KEY,
        monthly_price_usd            REAL NOT NULL DEFAULT 0,
        annual_price_usd             REAL NOT NULL DEFAULT 0,
        billing_period               TEXT NOT NULL DEFAULT 'annual',
        included_sites               INTEGER NOT NULL DEFAULT 1,
        included_ai_queries_month    INTEGER NOT NULL DEFAULT 0,
        included_backup_gb           REAL NOT NULL DEFAULT 0,
        included_support_minutes_month INTEGER NOT NULL DEFAULT 0,
        included_disk_gb             REAL NOT NULL DEFAULT 0,
        created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    # Seed plan_economics — idempotent via ON CONFLICT DO UPDATE
    """INSERT INTO plan_economics
        (plan_name, monthly_price_usd, annual_price_usd, included_sites,
         included_ai_queries_month, included_backup_gb, included_support_minutes_month, included_disk_gb)
       VALUES
        ('free',        0,   0,   1,   0,   0,   0,   1),
        ('personal',    9,  108,  1,  20,   2,  15,   5),
        ('negocio',    19,  228,  3, 100,  10,  30,  15),
        ('agencia',    39,  468, 10, 300,  30,  60,  50),
        ('agencia_pro', 59, 708, 25, 700,  75, 120, 100)
       ON CONFLICT (plan_name) DO UPDATE SET
        monthly_price_usd            = EXCLUDED.monthly_price_usd,
        annual_price_usd             = EXCLUDED.annual_price_usd,
        included_sites               = EXCLUDED.included_sites,
        included_ai_queries_month    = EXCLUDED.included_ai_queries_month,
        included_backup_gb           = EXCLUDED.included_backup_gb,
        included_support_minutes_month = EXCLUDED.included_support_minutes_month,
        included_disk_gb             = EXCLUDED.included_disk_gb,
        updated_at                   = NOW()
    """,

    # ── plan_economics: add new columns (idempotent) ─────────────────────────
    "ALTER TABLE plan_economics ADD COLUMN IF NOT EXISTS display_name TEXT",
    "ALTER TABLE plan_economics ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
    "ALTER TABLE plan_economics ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 99",

    # Backfill display_name + sort_order for existing plans
    """UPDATE plan_economics SET
        display_name = CASE plan_name
            WHEN 'free'        THEN 'Prueba Gratis'
            WHEN 'personal'    THEN 'Personal'
            WHEN 'negocio'     THEN 'Negocio'
            WHEN 'agencia'     THEN 'Agencia'
            WHEN 'agencia_pro' THEN 'Agencia Pro'
            ELSE display_name
        END,
        sort_order = CASE plan_name
            WHEN 'free'        THEN 0
            WHEN 'personal'    THEN 1
            WHEN 'negocio'     THEN 2
            WHEN 'agencia'     THEN 3
            WHEN 'agencia_pro' THEN 4
            ELSE sort_order
        END
    WHERE plan_name IN ('free', 'personal', 'negocio', 'agencia', 'agencia_pro')""",

    # Add enterprise plans
    """INSERT INTO plan_economics
        (plan_name, display_name, monthly_price_usd, annual_price_usd, billing_period,
         included_sites, included_ai_queries_month, included_backup_gb,
         included_support_minutes_month, included_disk_gb, is_active, sort_order)
       VALUES
        ('enterprise_annual',  'Enterprise Anual',   99,  1188, 'annual',  50, 1500, 200, 300, 250, TRUE, 5),
        ('enterprise_monthly', 'Enterprise Mensual', 129,    0, 'monthly', 50, 1500, 200, 300, 250, TRUE, 6)
       ON CONFLICT (plan_name) DO UPDATE SET
        display_name                   = EXCLUDED.display_name,
        monthly_price_usd              = EXCLUDED.monthly_price_usd,
        annual_price_usd               = EXCLUDED.annual_price_usd,
        billing_period                 = EXCLUDED.billing_period,
        included_sites                 = EXCLUDED.included_sites,
        included_ai_queries_month      = EXCLUDED.included_ai_queries_month,
        included_backup_gb             = EXCLUDED.included_backup_gb,
        included_support_minutes_month = EXCLUDED.included_support_minutes_month,
        included_disk_gb               = EXCLUDED.included_disk_gb,
        is_active                      = EXCLUDED.is_active,
        sort_order                     = EXCLUDED.sort_order,
        updated_at                     = NOW()
    """,

    # ── Unit-economics: server cost settings (singleton row id=1) ─────────────
    """CREATE TABLE IF NOT EXISTS cost_settings (
        id                           INTEGER PRIMARY KEY DEFAULT 1,
        monthly_server_cost_usd      REAL NOT NULL DEFAULT 18.98,
        total_vcpu                   REAL,
        total_ram_gb                 REAL,
        total_disk_gb                REAL,
        target_utilization_percent   REAL NOT NULL DEFAULT 70,
        cpu_cost_weight              REAL NOT NULL DEFAULT 0.40,
        ram_cost_weight              REAL NOT NULL DEFAULT 0.40,
        disk_cost_weight             REAL NOT NULL DEFAULT 0.15,
        overhead_cost_weight         REAL NOT NULL DEFAULT 0.05,
        backup_cost_per_gb_month_usd REAL NOT NULL DEFAULT 0.10,
        ai_cost_per_query_usd        REAL NOT NULL DEFAULT 0.02,
        human_support_hourly_cost_usd REAL NOT NULL DEFAULT 10,
        payment_fee_percent          REAL NOT NULL DEFAULT 6.5,
        payment_fee_fixed_usd        REAL NOT NULL DEFAULT 0.50,
        updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    """INSERT INTO cost_settings (id, monthly_server_cost_usd)
       VALUES (1, 18.98)
       ON CONFLICT (id) DO NOTHING""",
    # Seed hosting server capacity defaults (2 vCPU, 4 GB RAM, 80 GB disk)
    # COALESCE keeps any values already set by the admin
    """UPDATE cost_settings
       SET total_vcpu    = COALESCE(total_vcpu,    2),
           total_ram_gb  = COALESCE(total_ram_gb,  4),
           total_disk_gb = COALESCE(total_disk_gb, 80)
       WHERE id = 1""",
    # One-time cleanup: null out disk_mb samples that were collected via df instead
    # of du -sm. df reports the shared filesystem size (same for every container on
    # the same volume), producing identical ~11 GB values regardless of actual site size.
    # After 24 hours this UPDATE matches 0 rows and becomes a permanent no-op.
    """UPDATE hosting_resource_samples
       SET disk_mb = NULL
       WHERE sampled_at > NOW() - INTERVAL '24 hours'
         AND disk_mb > 1000
         AND container_name IN (
           'user_1_wp_canela-app_8cf5a9',
           'user_14_wp_tradingparaprincipiantes_91753e'
         )""",

    # custom_domains indexes
    "CREATE INDEX IF NOT EXISTS idx_custom_domains_hosting ON custom_domains(hosting_id)",
    "CREATE INDEX IF NOT EXISTS idx_custom_domains_user ON custom_domains(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_custom_domains_status ON custom_domains(dns_status, last_checked_at)",
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
