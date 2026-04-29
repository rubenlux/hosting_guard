"""
Security event logger with 5-minute deduplication window.

Usage:
    from app.services.security_event_service import log_security_event

    log_security_event(
        severity="warning",
        category="auth",
        event_type="AUTH_BRUTE_FORCE_IP",
        title="Fuerza bruta detectada",
        ip="1.2.3.4",
        source="scheduler",
    )

Dedup: if an open event with the same (category, event_type, ip, hosting_id)
exists within the last 5 minutes, its count is incremented and last_seen updated
instead of inserting a new row.

Never raises — errors are caught and logged.
"""
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_DEDUP_WINDOW_MINUTES = 5

# Severity escalation thresholds: (min_count, new_severity).
# Applied in order — first match wins for the *upgrade* direction only.
_ESCALATION: list[tuple[int, str]] = [
    (20, "critical"),
    (5,  "warning"),
]


def _escalated_severity(current: str, new_count: int) -> str:
    """Return escalated severity if count crosses a threshold, otherwise keep current."""
    _SEV_RANK = {"info": 0, "warning": 1, "critical": 2}
    current_rank = _SEV_RANK.get(current, 0)
    for min_count, target_sev in _ESCALATION:
        if new_count >= min_count:
            if _SEV_RANK.get(target_sev, 0) > current_rank:
                return target_sev
            break
    return current


def log_security_event(
    *,
    severity: str,
    category: str,
    event_type: str,
    title: str,
    message: Optional[str] = None,
    ip: Optional[str] = None,
    user_id: Optional[int] = None,
    hosting_id: Optional[int] = None,
    path: Optional[str] = None,
    user_agent: Optional[str] = None,
    source: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[int]:
    """Insert or increment a security event. Returns event_id (new or existing). Never raises."""
    from app.infra.db import get_connection, release_connection
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        meta_json = json.dumps(metadata or {})

        # ── Dedup update: target exactly the most recent matching open event ──
        # Using a subquery so we update ONE row (LIMIT 1) and can apply
        # severity escalation inside the same statement.
        cur.execute(
            """UPDATE security_events
               SET count     = count + 1,
                   last_seen = NOW(),
                   metadata  = CASE
                                 WHEN %s::jsonb != '{}'::jsonb
                                 THEN metadata || %s::jsonb
                                 ELSE metadata
                               END,
                   severity  = CASE
                                 WHEN count + 1 >= 20 AND severity != 'critical' THEN 'critical'
                                 WHEN count + 1 >= 5  AND severity = 'info'      THEN 'warning'
                                 ELSE severity
                               END
               WHERE event_id = (
                   SELECT event_id FROM security_events
                   WHERE  status     = 'open'
                     AND  category   = %s
                     AND  event_type = %s
                     AND  ip         IS NOT DISTINCT FROM %s
                     AND  hosting_id IS NOT DISTINCT FROM %s
                     AND  created_at >= NOW() - (%s || ' minutes')::INTERVAL
                   ORDER BY created_at DESC
                   LIMIT 1
               )
               RETURNING event_id, count, severity""",
            (
                meta_json, meta_json,
                category, event_type, ip, hosting_id,
                str(_DEDUP_WINDOW_MINUTES),
            ),
        )
        row = cur.fetchone()
        if row:
            conn.commit()
            # Notify if escalated to critical during dedup
            if row["severity"] == "critical":
                _notify_admin_critical(
                    row["event_id"], title, category, event_type, hosting_id, user_id
                )
            return row["event_id"]

        # ── No existing open event — insert fresh ────────────────────────────
        cur.execute(
            """INSERT INTO security_events
               (severity, category, event_type, title, message, ip, user_id,
                hosting_id, path, user_agent, source, metadata, count, last_seen)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, 1, NOW())
               RETURNING event_id""",
            (
                severity, category, event_type, title, message,
                ip, user_id, hosting_id, path, user_agent, source,
                meta_json,
            ),
        )
        row = cur.fetchone()
        conn.commit()
        event_id = row["event_id"] if row else None

        if event_id and severity == "critical":
            _notify_admin_critical(event_id, title, category, event_type, hosting_id, user_id)

        # Mirror to activity_events so Activity Log shows security events inline
        if event_id and user_id is not None:
            try:
                from app.services.activity_service import log_event
                log_event(
                    user_id=user_id,
                    hosting_id=hosting_id,
                    actor_type="system",
                    event_type=event_type,
                    category="security",
                    severity=severity,
                    title=title,
                    message=message,
                    ip=ip,
                    user_agent=user_agent,
                    source=source,
                    metadata={**(metadata or {}), "security_event_id": event_id},
                )
            except Exception:
                pass

        return event_id

    except Exception:
        logger.exception(
            "security_event_service: failed to log %s/%s", category, event_type
        )
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return None
    finally:
        if conn:
            release_connection(conn)


def _notify_admin_critical(
    event_id: int, title: str, category: str, event_type: str,
    hosting_id: Optional[int], user_id: Optional[int],
) -> None:
    """Fire notification to all admin users for critical security events."""
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
                f"Evento crítico detectado: {category}/{event_type} — Security Center #event_id:{event_id}",
                category="security",
                severity="critical",
                channel="both",
                action_url="/admin?section=security",
            )
    except Exception:
        logger.exception("security_event: admin notification failed for event_id=%s", event_id)


def resolve_security_event(event_id: int, resolved_by: int) -> bool:
    """Mark a security event as resolved. Returns True on success."""
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE security_events
               SET status = 'resolved', resolved_at = NOW(), resolved_by = %s
               WHERE event_id = %s AND status = 'open'""",
            (resolved_by, event_id),
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception:
        logger.exception("security_event: resolve failed for event_id=%s", event_id)
        conn.rollback()
        return False
    finally:
        release_connection(conn)


def query_security_events(
    severity: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    user_id: Optional[int] = None,
    hosting_id: Optional[int] = None,
    ip: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list:
    """Flexible query for security events. Returns list of dicts."""
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        clauses: list[str] = []
        params: list = []

        if severity:
            clauses.append("e.severity = %s"); params.append(severity)
        if category:
            clauses.append("e.category = %s"); params.append(category)
        if status:
            clauses.append("e.status = %s"); params.append(status)
        if user_id is not None:
            clauses.append("e.user_id = %s"); params.append(user_id)
        if hosting_id is not None:
            clauses.append("e.hosting_id = %s"); params.append(hosting_id)
        if ip:
            clauses.append("e.ip = %s"); params.append(ip)
        if date_from:
            clauses.append("e.created_at >= %s"); params.append(date_from)
        if date_to:
            clauses.append("e.created_at <= %s"); params.append(date_to)
        if search:
            clauses.append("(e.title ILIKE %s OR e.message ILIKE %s OR e.event_type ILIKE %s)")
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params += [limit, offset]

        cur = conn.cursor()
        cur.execute(
            f"""SELECT e.*, h.name AS hosting_name, h.subdomain,
                       u.email AS user_email
                FROM security_events e
                LEFT JOIN hostings h ON e.hosting_id = h.hosting_id
                LEFT JOIN users    u ON e.user_id    = u.user_id
                {where}
                ORDER BY e.created_at DESC
                LIMIT %s OFFSET %s""",
            params,
        )
        rows = cur.fetchall()
        result = []
        for r in rows:
            row = dict(r)
            if isinstance(row.get("metadata"), str):
                try:
                    row["metadata"] = json.loads(row["metadata"])
                except Exception:
                    row["metadata"] = {}
            result.append(row)
        return result
    finally:
        release_connection(conn)


def get_security_summary() -> dict:
    """Counts for Security Center dashboard cards."""
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cur = conn.cursor()

        # Overall open counts by severity
        cur.execute("""
            SELECT severity, COUNT(*) AS cnt
            FROM security_events
            WHERE status = 'open'
            GROUP BY severity
        """)
        severity_counts = {r["severity"]: r["cnt"] for r in cur.fetchall()}

        # Last 24 h counts by category
        cur.execute("""
            SELECT category, COUNT(*) AS cnt
            FROM security_events
            WHERE created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY category
        """)
        category_counts = {r["category"]: r["cnt"] for r in cur.fetchall()}

        # Active (open) events count
        cur.execute("SELECT COUNT(*) AS cnt FROM security_events WHERE status = 'open'")
        open_count = cur.fetchone()["cnt"]

        # Critical in last 24 h
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM security_events
            WHERE severity = 'critical' AND created_at >= NOW() - INTERVAL '24 hours'
        """)
        critical_24h = cur.fetchone()["cnt"]

        # Top attacked sites (hosting_id with most open events in last 24 h)
        cur.execute("""
            SELECT e.hosting_id, h.name, h.subdomain, COUNT(*) AS cnt
            FROM security_events e
            LEFT JOIN hostings h ON e.hosting_id = h.hosting_id
            WHERE e.hosting_id IS NOT NULL
              AND e.created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY e.hosting_id, h.name, h.subdomain
            ORDER BY cnt DESC
            LIMIT 5
        """)
        top_attacked = [dict(r) for r in cur.fetchall()]

        # Top suspect IPs
        cur.execute("""
            SELECT ip, COUNT(*) AS cnt, MAX(created_at) AS last_seen
            FROM security_events
            WHERE ip IS NOT NULL AND created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY ip
            ORDER BY cnt DESC
            LIMIT 10
        """)
        top_ips = [dict(r) for r in cur.fetchall()]

        # Determine overall threat level
        crit_open = severity_counts.get("critical", 0)
        warn_open = severity_counts.get("warning", 0)
        if crit_open > 0:
            threat_level = "under_attack"
        elif warn_open >= 3:
            threat_level = "warning"
        else:
            threat_level = "normal"

        return {
            "threat_level":       threat_level,
            "open_events":        open_count,
            "critical_24h":       critical_24h,
            "severity_counts":    severity_counts,
            "category_counts":    category_counts,
            "top_attacked_sites": top_attacked,
            "top_suspect_ips":    top_ips,
        }
    finally:
        release_connection(conn)


def get_total_count(
    severity: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
) -> int:
    """Count for pagination."""
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        clauses = []
        params = []
        if severity:
            clauses.append("severity = %s"); params.append(severity)
        if category:
            clauses.append("category = %s"); params.append(category)
        if status:
            clauses.append("status = %s"); params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) AS cnt FROM security_events {where}", params)
        return cur.fetchone()["cnt"]
    finally:
        release_connection(conn)
