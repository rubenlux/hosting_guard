"""
Security anomaly detection job.

Runs every 60 seconds. Queries existing tables for attack patterns and
creates security_events when thresholds are breached.

All rules are deterministic — no LLM required. The LLM is only invoked
optionally for incident summarization via the admin API.

Rules implemented:
  AUTH_BRUTE_FORCE_IP      — ≥10 failed logins from same IP in 10 min
  AUTH_BRUTE_FORCE_EMAIL   — ≥5  failed logins for same email in 10 min
  WP_LOGIN_BRUTE_FORCE     — ≥20 wp_login_failed events per hosting in 10 min
  WP_XMLRPC_ATTACK         — ≥10 wp_xmlrpc events per hosting in 10 min
  OWNERSHIP_PROBING        — ≥3  ownership_denied per user/IP in 30 min
  WEBHOOK_ATTACK           — ≥3  invalid_webhook_signature per IP in 10 min
  UPLOAD_ATTACK            — ≥3  upload_rejected per user in 30 min
  RESOURCE_ABUSE           — ≥10 throttle orchestrator events per container in 15 min
  ERROR_SPIKE              — 5xx rate > 5 % sustained in last collection window
  RATE_LIMIT_ABUSE         — ≥10 rate_limit_hit per IP in 5 min
  WP_USER_ESCALATION       — wp_user_role_changed to admin in last 10 min
  WP_CORE_UPDATE           — unexpected WordPress core update event
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def detect_security_anomalies() -> None:
    """Entry point called by the scheduler every 60 s."""
    try:
        _rule_auth_brute_force_ip()
        _rule_auth_brute_force_email()
        _rule_wp_login_brute_force()
        _rule_wp_xmlrpc_attack()
        _rule_ownership_probing()
        _rule_webhook_attack()
        _rule_upload_attack()
        _rule_resource_abuse()
        _rule_error_spike()
        _rule_rate_limit_abuse()
        _rule_wp_privilege_escalation()
    except Exception as exc:
        logger.exception("detect_security_anomalies: uncaught exception: %s", exc)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _log(
    severity: str,
    category: str,
    event_type: str,
    title: str,
    *,
    message: Optional[str] = None,
    ip: Optional[str] = None,
    user_id: Optional[int] = None,
    hosting_id: Optional[int] = None,
    metadata: Optional[dict] = None,
) -> None:
    from app.services.security_event_service import log_security_event
    log_security_event(
        severity=severity, category=category, event_type=event_type,
        title=title, message=message, ip=ip, user_id=user_id,
        hosting_id=hosting_id, source="scheduler", metadata=metadata,
    )


def _query(sql: str, params: tuple = ()) -> list:
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)


# ─── Rule implementations ────────────────────────────────────────────────────

def _rule_auth_brute_force_ip() -> None:
    rows = _query("""
        SELECT ip, COUNT(*) AS cnt
        FROM login_audit
        WHERE success = 0
          AND created_at::TIMESTAMPTZ >= NOW() - INTERVAL '10 minutes'
          AND ip IS NOT NULL
        GROUP BY ip
        HAVING COUNT(*) >= 10
    """)
    for r in rows:
        _log(
            "critical", "auth", "AUTH_BRUTE_FORCE_IP",
            f"Fuerza bruta en login: {r['cnt']} intentos desde {r['ip']}",
            message=f"IP {r['ip']} realizó {r['cnt']} intentos fallidos de login en los últimos 10 minutos.",
            ip=r["ip"],
            metadata={"attempt_count": r["cnt"], "window_minutes": 10},
        )


def _rule_auth_brute_force_email() -> None:
    rows = _query("""
        SELECT email, COUNT(*) AS cnt
        FROM login_audit
        WHERE success = 0
          AND created_at::TIMESTAMPTZ >= NOW() - INTERVAL '10 minutes'
          AND email IS NOT NULL
        GROUP BY email
        HAVING COUNT(*) >= 5
    """)
    for r in rows:
        _log(
            "warning", "auth", "AUTH_BRUTE_FORCE_EMAIL",
            f"Múltiples intentos fallidos en cuenta: {r['email']}",
            message=f"{r['cnt']} intentos fallidos de login en los últimos 10 minutos para {r['email']}.",
            metadata={"email": r["email"], "attempt_count": r["cnt"], "window_minutes": 10},
        )


def _rule_wp_login_brute_force() -> None:
    rows = _query("""
        SELECT hosting_id, COUNT(*) AS cnt, MAX(ip) AS last_ip
        FROM activity_events
        WHERE event_type  = 'wp_login_failed'
          AND category    = 'auth'
          AND created_at >= NOW() - INTERVAL '10 minutes'
          AND hosting_id IS NOT NULL
        GROUP BY hosting_id
        HAVING COUNT(*) >= 20
    """)
    for r in rows:
        _log(
            "critical", "wordpress_auth", "WP_LOGIN_BRUTE_FORCE",
            f"Fuerza bruta en wp-login.php (hosting:{r['hosting_id']})",
            message=f"{r['cnt']} intentos de login WordPress en 10 minutos.",
            hosting_id=r["hosting_id"],
            ip=r.get("last_ip"),
            metadata={"attempt_count": r["cnt"], "window_minutes": 10},
        )


def _rule_wp_xmlrpc_attack() -> None:
    rows = _query("""
        SELECT hosting_id, COUNT(*) AS cnt, MAX(ip) AS last_ip
        FROM activity_events
        WHERE event_type  = 'wp_xmlrpc_attack'
          AND created_at >= NOW() - INTERVAL '10 minutes'
          AND hosting_id IS NOT NULL
        GROUP BY hosting_id
        HAVING COUNT(*) >= 10
    """)
    for r in rows:
        _log(
            "warning", "wordpress_auth", "XMLRPC_ATTACK",
            f"Ataque XML-RPC detectado (hosting:{r['hosting_id']})",
            message=f"{r['cnt']} peticiones a xmlrpc.php en 10 minutos.",
            hosting_id=r["hosting_id"],
            ip=r.get("last_ip"),
            metadata={"request_count": r["cnt"]},
        )


def _rule_ownership_probing() -> None:
    # By user_id
    rows_user = _query("""
        SELECT user_id, COUNT(*) AS cnt, MAX(ip) AS last_ip
        FROM activity_events
        WHERE event_type  = 'ownership_denied'
          AND created_at >= NOW() - INTERVAL '30 minutes'
          AND user_id IS NOT NULL
        GROUP BY user_id
        HAVING COUNT(*) >= 3
    """)
    for r in rows_user:
        _log(
            "warning", "ownership", "OWNERSHIP_PROBING",
            f"Acceso a recursos ajenos: usuario {r['user_id']}",
            message=f"Usuario {r['user_id']} intentó acceder a recursos que no le pertenecen {r['cnt']} veces en 30 min.",
            user_id=r["user_id"],
            ip=r.get("last_ip"),
            metadata={"probe_count": r["cnt"], "window_minutes": 30},
        )

    # By IP (may catch unauthenticated probes)
    rows_ip = _query("""
        SELECT ip, COUNT(*) AS cnt
        FROM activity_events
        WHERE event_type  = 'ownership_denied'
          AND created_at >= NOW() - INTERVAL '30 minutes'
          AND ip IS NOT NULL
        GROUP BY ip
        HAVING COUNT(*) >= 3
    """)
    for r in rows_ip:
        _log(
            "warning", "ownership", "OWNERSHIP_PROBING_IP",
            f"Acceso a recursos ajenos desde IP: {r['ip']}",
            message=f"IP {r['ip']} generó {r['cnt']} errores de propiedad en 30 min.",
            ip=r["ip"],
            metadata={"probe_count": r["cnt"], "window_minutes": 30},
        )


def _rule_webhook_attack() -> None:
    rows = _query("""
        SELECT ip, COUNT(*) AS cnt
        FROM activity_events
        WHERE event_type  IN ('invalid_webhook_signature', 'webhook_attack')
          AND created_at >= NOW() - INTERVAL '10 minutes'
          AND ip IS NOT NULL
        GROUP BY ip
        HAVING COUNT(*) >= 3
    """)
    for r in rows:
        _log(
            "warning", "webhook", "WEBHOOK_ATTACK",
            f"Webhooks inválidos desde {r['ip']}",
            message=f"{r['cnt']} webhooks con firma inválida en 10 minutos desde {r['ip']}.",
            ip=r["ip"],
            metadata={"invalid_count": r["cnt"]},
        )


def _rule_upload_attack() -> None:
    rows = _query("""
        SELECT user_id, COUNT(*) AS cnt, MAX(ip) AS last_ip
        FROM activity_events
        WHERE event_type  IN ('upload_rejected', 'magic_bytes_rejected', 'upload_attack')
          AND created_at >= NOW() - INTERVAL '30 minutes'
          AND user_id IS NOT NULL
        GROUP BY user_id
        HAVING COUNT(*) >= 3
    """)
    for r in rows:
        _log(
            "warning", "upload", "UPLOAD_ATTACK",
            f"Múltiples uploads maliciosos bloqueados (user:{r['user_id']})",
            message=f"Usuario {r['user_id']} tuvo {r['cnt']} uploads rechazados por contenido inválido en 30 min.",
            user_id=r["user_id"],
            ip=r.get("last_ip"),
            metadata={"rejected_count": r["cnt"], "window_minutes": 30},
        )


def _rule_resource_abuse() -> None:
    rows = _query("""
        SELECT oe.container_name, oe.user_id, COUNT(*) AS cnt
        FROM orchestrator_events oe
        WHERE oe.event_type = 'throttle'
          AND oe.created_at >= NOW() - INTERVAL '15 minutes'
          AND oe.user_id IS NOT NULL
        GROUP BY oe.container_name, oe.user_id
        HAVING COUNT(*) >= 10
    """)
    for r in rows:
        # Resolve hosting_id from container_name
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT hosting_id FROM hostings WHERE container_name = %s",
                (r["container_name"],),
            )
            h = cur.fetchone()
            hosting_id = h["hosting_id"] if h else None
        finally:
            release_connection(conn)

        _log(
            "warning", "resource_abuse", "RESOURCE_ABUSE",
            f"Abuso de recursos: {r['container_name']} ({r['cnt']} throttles en 15min)",
            message=f"Contenedor {r['container_name']} fue throttleado {r['cnt']} veces en 15 min.",
            user_id=r.get("user_id"),
            hosting_id=hosting_id,
            metadata={"throttle_count": r["cnt"], "container": r["container_name"]},
        )


def _rule_error_spike() -> None:
    rows = _query("""
        SELECT container_name,
               SUM(total_requests) AS total,
               SUM(errors_5xx)     AS e5xx,
               MAX(collected_at)   AS last_at
        FROM traffic_stats
        WHERE collected_at::TIMESTAMPTZ >= NOW() - INTERVAL '10 minutes'
          AND total_requests > 20
        GROUP BY container_name
        HAVING SUM(total_requests) > 0
           AND SUM(errors_5xx)::FLOAT / NULLIF(SUM(total_requests), 0) > 0.05
    """)
    for r in rows:
        pct = int(100 * r["e5xx"] / r["total"]) if r["total"] else 0
        from app.infra.db import get_connection, release_connection
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT hosting_id, user_id FROM hostings WHERE container_name = %s",
                (r["container_name"],),
            )
            h = cur.fetchone()
            hosting_id = h["hosting_id"] if h else None
            user_id    = h["user_id"]    if h else None
        finally:
            release_connection(conn)

        _log(
            "warning", "traffic_anomaly", "ERROR_SPIKE",
            f"Spike de errores 5xx: {pct}% en {r['container_name']}",
            message=f"{r['e5xx']} errores 5xx de {r['total']} requests en los últimos 10 minutos ({pct}%).",
            hosting_id=hosting_id,
            user_id=user_id,
            metadata={"total_requests": r["total"], "errors_5xx": r["e5xx"], "error_pct": pct},
        )


def _rule_rate_limit_abuse() -> None:
    rows = _query("""
        SELECT ip, COUNT(*) AS cnt
        FROM activity_events
        WHERE event_type  = 'rate_limit_hit'
          AND created_at >= NOW() - INTERVAL '5 minutes'
          AND ip IS NOT NULL
        GROUP BY ip
        HAVING COUNT(*) >= 10
    """)
    for r in rows:
        _log(
            "warning", "api", "RATE_LIMIT_ABUSE",
            f"Abuso de rate-limit desde {r['ip']}",
            message=f"IP {r['ip']} alcanzó el rate-limit {r['cnt']} veces en 5 minutos.",
            ip=r["ip"],
            metadata={"hit_count": r["cnt"], "window_minutes": 5},
        )


def _rule_wp_privilege_escalation() -> None:
    rows = _query("""
        SELECT hosting_id, user_id, ip, metadata
        FROM activity_events
        WHERE event_type  = 'wp_user_role_changed'
          AND created_at >= NOW() - INTERVAL '10 minutes'
          AND hosting_id IS NOT NULL
          AND metadata->>'new_role' = 'administrator'
    """)
    for r in rows:
        _log(
            "critical", "wordpress_auth", "WP_PRIVILEGE_ESCALATION",
            f"Escalada de privilegios WordPress (hosting:{r['hosting_id']})",
            message="Un usuario fue promovido a administrador en WordPress. Verificar si fue intencional.",
            hosting_id=r["hosting_id"],
            user_id=r.get("user_id"),
            ip=r.get("ip"),
            metadata=r.get("metadata") or {},
        )
