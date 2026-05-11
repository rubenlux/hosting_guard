"""
WordPress attack aggregator.

Runs every 65 s with initial_delay=25 s (fires after collect_wp_log_attacks
has had time to insert activity_events). Aggregates those rows per hosting
and upserts security_events.

Upsert: INSERT ... ON CONFLICT (event_type, hosting_id) WHERE status='open'
DO UPDATE — guaranteed by unique partial index uq_open_wp_security_event.
One open incident per (event_type, hosting_id), no duplicates.

Rules:
  WP_LOGIN_BRUTE_FORCE  — ≥5  wp_login_failed rows per hosting in 10 min
  XMLRPC_ATTACK         — ≥3  xmlrpc rows per hosting in 10 min
"""
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_WINDOW_MINUTES     = 10
_WP_LOGIN_THRESHOLD = 5
_XMLRPC_THRESHOLD   = 3

_RATE_LIMIT_THRESHOLD = int(os.getenv("WP_LOGIN_RATE_LIMIT_MAX_POSTS", "5"))
_RATE_LIMIT_WINDOW    = int(os.getenv("WP_LOGIN_RATE_LIMIT_WINDOW_MINUTES", "10"))


# ─── Severity helpers ─────────────────────────────────────────────────────────

def _sev_wp_login(count: int) -> str:
    if count >= 20:
        return "critical"
    if count >= 10:
        return "warning"
    return "warning"


def _sev_xmlrpc(count: int) -> str:
    return "critical" if count >= 10 else "warning"


def _sev_rate_limit(count: int) -> str:
    return "warning"


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
    last_event_ts,
) -> str:
    """INSERT ... ON CONFLICT DO UPDATE keyed on (event_type, hosting_id) WHERE status='open'.

    Returns 'created' or 'updated'. Raises on DB error so the caller can log and skip.
    """
    from app.infra.db import get_connection, release_connection
    severity = severity_fn(failed_attempts)
    meta = {
        "container_name":    container_name,
        "hosting_id":        hosting_id,
        "window_minutes":    _WINDOW_MINUTES,
        "failed_attempt_rows": failed_attempts,
        "source":            "activity_events",
        "rule":              event_type.lower(),
    }
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO security_events
              (event_type, category, severity, title, message,
               hosting_id, user_id, ip, source, metadata, count, last_seen)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'scheduler', %s::jsonb, %s, %s)
            ON CONFLICT (event_type, hosting_id) WHERE status = 'open'
            DO UPDATE SET
              count     = EXCLUDED.count,
              severity  = EXCLUDED.severity,
              last_seen = GREATEST(security_events.last_seen, EXCLUDED.last_seen),
              metadata  = security_events.metadata || EXCLUDED.metadata,
              ip        = COALESCE(EXCLUDED.ip, security_events.ip)
            RETURNING event_id, (xmax::bigint = 0) AS is_new
            """,
            (
                event_type, category, severity, title, message,
                hosting_id, user_id, last_ip,
                json.dumps(meta), failed_attempts, last_event_ts,
            ),
        )
        row = cur.fetchone()
        conn.commit()

        if row and severity == "critical" and row["is_new"]:
            _notify_critical(row["event_id"], title, category, event_type, hosting_id, user_id)

        return "created" if (row and row["is_new"]) else "updated"
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
                category="security", severity="critical",
                channel="both", action_url="/admin?section=security",
            )
    except Exception as exc:
        logger.warning("aggregate_wp_attacks: admin notification failed: %s", exc)


# ─── Rules ────────────────────────────────────────────────────────────────────

def _rule_wp_login() -> tuple[int, int, int]:
    """Return (created, updated, skipped)."""
    rows = _query(
        """
        SELECT ae.hosting_id,
               h.user_id,
               h.container_name,
               COUNT(*)           AS cnt,
               MAX(ae.ip)         AS last_ip,
               MAX(ae.created_at) AS last_event
        FROM   activity_events ae
        JOIN   hostings h ON h.hosting_id = ae.hosting_id
        WHERE  ae.event_type  = 'wp_login_failed'
          AND  ae.created_at >= NOW() - (%s || ' minutes')::INTERVAL
          AND  ae.hosting_id IS NOT NULL
          AND  h.status NOT IN ('deleted', 'expired')
        GROUP  BY ae.hosting_id, h.user_id, h.container_name
        """,
        (str(_WINDOW_MINUTES),),
    )

    if not rows:
        return 0, 0, 0

    above   = [r for r in rows if r["cnt"] >= _WP_LOGIN_THRESHOLD]
    skipped = [r for r in rows if r["cnt"] < _WP_LOGIN_THRESHOLD]

    logger.info(
        "aggregate_wp_attacks: wp_login — %d hosting(s) with events "
        "(%d above threshold=%d, %d below)",
        len(rows), len(above), _WP_LOGIN_THRESHOLD, len(skipped),
    )

    for r in skipped:
        logger.debug(
            "aggregate_wp_attacks: wp_login SKIP hosting_id=%s (%s): %d rows < threshold %d",
            r.get("hosting_id"), r.get("container_name"), r["cnt"], _WP_LOGIN_THRESHOLD,
        )

    created = updated = 0
    for r in above:
        cname = r.get("container_name") or "unknown"
        logger.info(
            "aggregate_wp_attacks: wp_login hosting_id=%s (%s): %d rows → WP_LOGIN_BRUTE_FORCE",
            r["hosting_id"], cname, r["cnt"],
        )
        try:
            action = _upsert(
                event_type      = "WP_LOGIN_BRUTE_FORCE",
                category        = "wordpress_auth",
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
                last_event_ts   = r["last_event"],
            )
            logger.info(
                "aggregate_wp_attacks: WP_LOGIN_BRUTE_FORCE %s for hosting_id=%s",
                action.upper(), r["hosting_id"],
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

    return created, updated, len(skipped)


def _rule_xmlrpc() -> tuple[int, int, int]:
    """Return (created, updated, skipped)."""
    rows = _query(
        """
        SELECT ae.hosting_id,
               h.user_id,
               h.container_name,
               COUNT(*)           AS cnt,
               MAX(ae.ip)         AS last_ip,
               MAX(ae.created_at) AS last_event
        FROM   activity_events ae
        JOIN   hostings h ON h.hosting_id = ae.hosting_id
        WHERE  ae.event_type   ILIKE %s
          AND  ae.created_at  >= NOW() - (%s || ' minutes')::INTERVAL
          AND  ae.hosting_id  IS NOT NULL
          AND  h.status NOT IN ('deleted', 'expired')
        GROUP  BY ae.hosting_id, h.user_id, h.container_name
        """,
        ("%xmlrpc%", str(_WINDOW_MINUTES)),
    )

    if not rows:
        return 0, 0, 0

    above   = [r for r in rows if r["cnt"] >= _XMLRPC_THRESHOLD]
    skipped = [r for r in rows if r["cnt"] < _XMLRPC_THRESHOLD]

    logger.info(
        "aggregate_wp_attacks: xmlrpc — %d hosting(s) with events "
        "(%d above threshold=%d, %d below)",
        len(rows), len(above), _XMLRPC_THRESHOLD, len(skipped),
    )

    for r in skipped:
        logger.debug(
            "aggregate_wp_attacks: xmlrpc SKIP hosting_id=%s (%s): %d rows < threshold %d",
            r.get("hosting_id"), r.get("container_name"), r["cnt"], _XMLRPC_THRESHOLD,
        )

    created = updated = 0
    for r in above:
        cname = r.get("container_name") or "unknown"
        logger.info(
            "aggregate_wp_attacks: xmlrpc hosting_id=%s (%s): %d rows → XMLRPC_ATTACK",
            r["hosting_id"], cname, r["cnt"],
        )
        try:
            action = _upsert(
                event_type      = "XMLRPC_ATTACK",
                category        = "wordpress_auth",
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
                last_event_ts   = r["last_event"],
            )
            logger.info(
                "aggregate_wp_attacks: XMLRPC_ATTACK %s for hosting_id=%s",
                action.upper(), r["hosting_id"],
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

    return created, updated, len(skipped)


def _rule_wp_login_rate_limit() -> tuple[int, int, int]:
    """Per-IP per-hosting rate limit detection.

    If a single IP accumulates >= _RATE_LIMIT_THRESHOLD wp_login_failed events
    in _RATE_LIMIT_WINDOW minutes, upsert a WP_LOGIN_RATE_LIMITED security event.
    Returns (created, updated, skipped).
    """
    rows = _query(
        """
        SELECT ae.hosting_id,
               h.user_id,
               h.container_name,
               ae.ip,
               COUNT(*)           AS cnt,
               MAX(ae.created_at) AS last_event
        FROM   activity_events ae
        JOIN   hostings h ON h.hosting_id = ae.hosting_id
        WHERE  ae.event_type = 'wp_login_failed'
          AND  ae.created_at >= NOW() - (%s || ' minutes')::INTERVAL
          AND  ae.hosting_id IS NOT NULL
          AND  ae.ip IS NOT NULL
          AND  h.status NOT IN ('deleted', 'expired')
        GROUP  BY ae.hosting_id, h.user_id, h.container_name, ae.ip
        """,
        (str(_RATE_LIMIT_WINDOW),),
    )

    if not rows:
        return 0, 0, 0

    above   = [r for r in rows if r["cnt"] >= _RATE_LIMIT_THRESHOLD]
    skipped = [r for r in rows if r["cnt"] < _RATE_LIMIT_THRESHOLD]

    logger.info(
        "aggregate_wp_attacks: rate_limit — %d ip×hosting combos "
        "(%d above threshold=%d, %d below)",
        len(rows), len(above), _RATE_LIMIT_THRESHOLD, len(skipped),
    )

    created = updated = 0
    for r in above:
        cname = r.get("container_name") or "unknown"
        offending_ip = r.get("ip") or "desconocida"
        logger.info(
            "aggregate_wp_attacks: rate_limit hosting_id=%s (%s) ip=%s: %d rows → WP_LOGIN_RATE_LIMITED",
            r["hosting_id"], cname, offending_ip, r["cnt"],
        )
        try:
            action = _upsert(
                event_type      = "WP_LOGIN_RATE_LIMITED",
                category        = "wordpress_auth",
                severity_fn     = _sev_rate_limit,
                title           = f"IP con exceso de intentos de login: {cname}",
                message         = (
                    f"IP {offending_ip}: {r['cnt']} intentos fallidos de login "
                    f"en los últimos {_RATE_LIMIT_WINDOW} minutos en {cname}."
                ),
                hosting_id      = r["hosting_id"],
                user_id         = r.get("user_id"),
                last_ip         = r.get("ip"),
                failed_attempts = r["cnt"],
                container_name  = cname,
                last_event_ts   = r["last_event"],
            )
            logger.info(
                "aggregate_wp_attacks: WP_LOGIN_RATE_LIMITED %s for hosting_id=%s ip=%s",
                action.upper(), r["hosting_id"], offending_ip,
            )
            if action == "created":
                created += 1
            else:
                updated += 1
        except Exception as exc:
            logger.warning(
                "aggregate_wp_attacks: rate_limit upsert failed for hosting_id=%s (%s): %s",
                r.get("hosting_id"), cname, exc,
            )

    return created, updated, len(skipped)


# ─── Entry point ──────────────────────────────────────────────────────────────

def aggregate_wp_attacks() -> None:
    """Called by the scheduler every 65 s with initial_delay=25 s."""
    lc = lu = ls = 0
    xc = xu = xs = 0
    rc = ru = rs = 0

    try:
        lc, lu, ls = _rule_wp_login()
    except Exception as exc:
        logger.exception("aggregate_wp_attacks: _rule_wp_login failed: %s", exc)

    try:
        xc, xu, xs = _rule_xmlrpc()
    except Exception as exc:
        logger.exception("aggregate_wp_attacks: _rule_xmlrpc failed: %s", exc)

    try:
        rc, ru, rs = _rule_wp_login_rate_limit()
    except Exception as exc:
        logger.exception("aggregate_wp_attacks: _rule_wp_login_rate_limit failed: %s", exc)

    logger.info(
        "aggregate_wp_attacks summary: "
        "wp_login_created=%d wp_login_updated=%d wp_login_skipped=%d "
        "xmlrpc_created=%d xmlrpc_updated=%d xmlrpc_skipped=%d "
        "rate_limit_created=%d rate_limit_updated=%d rate_limit_skipped=%d",
        lc, lu, ls, xc, xu, xs, rc, ru, rs,
    )
