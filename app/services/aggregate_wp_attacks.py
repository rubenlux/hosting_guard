"""
WordPress attack aggregator.

Runs every 65 s (5 s after collect_wp_log_attacks). Reads activity_events
rows inserted by that collector and upserts security_events per hosting.

Upsert key: (event_type, hosting_id, status='open') with last_seen within
_INCIDENT_TTL_MIN — rolling window that keeps the incident alive as long as
attacks continue hitting the collector every 60 s.

Rules:
  WP_LOGIN_BRUTE_FORCE  — ≥5  wp_login_failed rows per hosting in 10 min
  XMLRPC_ATTACK         — ≥3  wp_xmlrpc_attack rows per hosting in 10 min
"""
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_WINDOW_MINUTES   = 10   # lookback window for activity_events
_INCIDENT_TTL_MIN = 60   # roll into same open incident if last_seen within this

_WP_LOGIN_THRESHOLD = 5
_XMLRPC_THRESHOLD   = 3


# ─── Severity helpers ─────────────────────────────────────────────────────────

def _sev_wp_login(count: int) -> str:
    if count >= 20:
        return "critical"
    if count >= 10:
        return "high"
    return "medium"


def _sev_xmlrpc(count: int) -> str:
    return "critical" if count >= 10 else "high"


# ─── DB helpers ───────────────────────────────────────────────────────────────

def _query(sql: str, params: tuple) -> list[dict]:
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)


def _upsert(
    *,
    event_type: str,
    category: str,
    severity_fn,
    title: str,
    message: str,
    hosting_id: int,
    user_id: Optional[int],
    last_ip: Optional[str],
    failed_attempts: int,
    container_name: str,
) -> str:
    """Upsert a security_event keyed on (event_type, hosting_id) using rolling TTL.

    Returns 'created' or 'updated'.
    Raises on DB error so the caller can log and continue.
    """
    from app.infra.db import get_connection, release_connection
    meta = {
        "container_name":  container_name,
        "window_minutes":  _WINDOW_MINUTES,
        "failed_attempts": failed_attempts,
    }
    conn = get_connection()
    try:
        cur = conn.cursor()

        # Look for an open incident still active (last_seen within TTL)
        cur.execute(
            """
            SELECT event_id, count, severity
            FROM   security_events
            WHERE  event_type  = %s
              AND  hosting_id  = %s
              AND  status      = 'open'
              AND  last_seen  >= NOW() - (%s || ' minutes')::INTERVAL
            ORDER  BY created_at DESC
            LIMIT  1
            """,
            (event_type, hosting_id, str(_INCIDENT_TTL_MIN)),
        )
        existing = cur.fetchone()

        if existing:
            new_count = max(existing["count"], failed_attempts)
            new_sev   = severity_fn(new_count)
            cur.execute(
                """
                UPDATE security_events
                SET    count     = %s,
                       last_seen = NOW(),
                       severity  = %s,
                       ip        = COALESCE(%s, ip),
                       metadata  = metadata || %s::jsonb
                WHERE  event_id  = %s
                """,
                (new_count, new_sev, last_ip, json.dumps(meta), existing["event_id"]),
            )
            conn.commit()
            return "updated"

        # No active incident — insert a fresh one
        severity = severity_fn(failed_attempts)
        cur.execute(
            """
            INSERT INTO security_events
              (event_type, category, severity, title, message,
               hosting_id, user_id, ip, source, metadata, count, last_seen)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'scheduler', %s::jsonb, %s, NOW())
            RETURNING event_id
            """,
            (
                event_type, category, severity, title, message,
                hosting_id, user_id, last_ip,
                json.dumps(meta), failed_attempts,
            ),
        )
        row = cur.fetchone()
        conn.commit()

        if row and severity == "critical":
            _notify_critical(row["event_id"], title, category, event_type, hosting_id, user_id)

        return "created"
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        release_connection(conn)


def _notify_critical(
    event_id: int,
    title: str,
    category: str,
    event_type: str,
    hosting_id: Optional[int],
    user_id: Optional[int],
) -> None:
    try:
        from app.infra.db import get_connection, release_connection
        from app.services.notification_service import notify
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM users WHERE role = 'admin'")
            admin_ids = [r["user_id"] for r in cur.fetchall()]
        finally:
            release_connection(conn)
        for aid in admin_ids:
            notify(
                aid,
                f"[SECURITY] {title}",
                f"Evento crítico detectado: {category}/{event_type}",
                category="security",
                severity="critical",
                channel="both",
                action_url="/admin?section=security",
            )
    except Exception as exc:
        logger.warning("aggregate_wp_attacks: admin notification failed: %s", exc)


# ─── Rules ────────────────────────────────────────────────────────────────────

def _rule_wp_login() -> tuple[int, int]:
    """Return (created, updated) counts."""
    rows = _query(
        """
        SELECT ae.hosting_id,
               h.user_id,
               h.container_name,
               COUNT(*)        AS cnt,
               MAX(ae.ip)      AS last_ip
        FROM   activity_events ae
        JOIN   hostings         h ON h.hosting_id = ae.hosting_id
        WHERE  ae.event_type  = 'wp_login_failed'
          AND  ae.created_at >= NOW() - (%s || ' minutes')::INTERVAL
          AND  ae.hosting_id IS NOT NULL
          AND  h.status NOT IN ('deleted', 'expired')
        GROUP  BY ae.hosting_id, h.user_id, h.container_name
        HAVING COUNT(*) >= %s
        """,
        (str(_WINDOW_MINUTES), _WP_LOGIN_THRESHOLD),
    )

    if not rows:
        return 0, 0

    logger.info("aggregate_wp_attacks: wp_login_failed — %d hosting(s) above threshold", len(rows))
    created = updated = 0

    for r in rows:
        cname = r.get("container_name") or "unknown"
        try:
            action = _upsert(
                event_type      = "WP_LOGIN_BRUTE_FORCE",
                category        = "wordpress",
                severity_fn     = _sev_wp_login,
                title           = f"Intentos repetidos de login WordPress: {cname}",
                message         = (
                    f"{r['cnt']} eventos de wp-login.php en los últimos "
                    f"{_WINDOW_MINUTES} minutos en {cname}."
                ),
                hosting_id      = r["hosting_id"],
                user_id         = r.get("user_id"),
                last_ip         = r.get("last_ip"),
                failed_attempts = r["cnt"],
                container_name  = cname,
            )
            if action == "created":
                created += 1
            else:
                updated += 1
        except Exception as exc:
            logger.warning(
                "aggregate_wp_attacks: WP_LOGIN upsert failed for hosting_id=%s (%s): %s",
                r.get("hosting_id"), cname, exc,
            )

    return created, updated


def _rule_xmlrpc() -> tuple[int, int]:
    """Return (created, updated) counts."""
    rows = _query(
        """
        SELECT ae.hosting_id,
               h.user_id,
               h.container_name,
               COUNT(*)        AS cnt,
               MAX(ae.ip)      AS last_ip
        FROM   activity_events ae
        JOIN   hostings         h ON h.hosting_id = ae.hosting_id
        WHERE  ae.event_type   ILIKE %s
          AND  ae.created_at  >= NOW() - (%s || ' minutes')::INTERVAL
          AND  ae.hosting_id  IS NOT NULL
          AND  h.status NOT IN ('deleted', 'expired')
        GROUP  BY ae.hosting_id, h.user_id, h.container_name
        HAVING COUNT(*) >= %s
        """,
        ("%xmlrpc%", str(_WINDOW_MINUTES), _XMLRPC_THRESHOLD),
    )

    if not rows:
        return 0, 0

    logger.info("aggregate_wp_attacks: xmlrpc — %d hosting(s) above threshold", len(rows))
    created = updated = 0

    for r in rows:
        cname = r.get("container_name") or "unknown"
        try:
            action = _upsert(
                event_type      = "XMLRPC_ATTACK",
                category        = "wordpress",
                severity_fn     = _sev_xmlrpc,
                title           = f"Ataque XML-RPC detectado: {cname}",
                message         = (
                    f"{r['cnt']} peticiones a xmlrpc.php en los últimos "
                    f"{_WINDOW_MINUTES} minutos en {cname}."
                ),
                hosting_id      = r["hosting_id"],
                user_id         = r.get("user_id"),
                last_ip         = r.get("last_ip"),
                failed_attempts = r["cnt"],
                container_name  = cname,
            )
            if action == "created":
                created += 1
            else:
                updated += 1
        except Exception as exc:
            logger.warning(
                "aggregate_wp_attacks: XMLRPC upsert failed for hosting_id=%s (%s): %s",
                r.get("hosting_id"), cname, exc,
            )

    return created, updated


# ─── Entry point ──────────────────────────────────────────────────────────────

def aggregate_wp_attacks() -> None:
    """Called by the scheduler every 65 s (5 s after collect_wp_log_attacks)."""
    login_created = login_updated = 0
    xmlrpc_created = xmlrpc_updated = 0

    try:
        login_created, login_updated = _rule_wp_login()
    except Exception as exc:
        logger.exception("aggregate_wp_attacks: _rule_wp_login failed: %s", exc)

    try:
        xmlrpc_created, xmlrpc_updated = _rule_xmlrpc()
    except Exception as exc:
        logger.exception("aggregate_wp_attacks: _rule_xmlrpc failed: %s", exc)

    total_created = login_created  + xmlrpc_created
    total_updated = login_updated  + xmlrpc_updated

    if total_created or total_updated:
        logger.info(
            "aggregate_wp_attacks: security_events created=%d updated=%d "
            "(wp_login: +%d/~%d  xmlrpc: +%d/~%d)",
            total_created, total_updated,
            login_created,  login_updated,
            xmlrpc_created, xmlrpc_updated,
        )
