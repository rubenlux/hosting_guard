"""
WordPress attack log collector.

Runs every 60 s (via scheduler_runner). Reads the last 90 seconds of Nginx
access logs from every active WordPress container, detects wp-login.php POST
and xmlrpc.php requests, and inserts activity_events so the existing
detect_security_anomalies rules fire: WP_LOGIN_BRUTE_FORCE / XMLRPC_ATTACK.

Container selection: only containers matching the 'user_*_wp_*' naming pattern
(WordPress containers). Git/static containers don't run WordPress.
"""
import logging
import re
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

_WP_LOGIN_RE = re.compile(r'"POST /wp-login\.php', re.IGNORECASE)
# Match ALL requests to xmlrpc.php (including 403s already blocked by hardening)
_XMLRPC_RE   = re.compile(r'"/xmlrpc\.php', re.IGNORECASE)
# Extract IP from combined log format: first field before space
_IP_RE       = re.compile(r'^(\S+)')


def _get_wp_containers() -> list[dict]:
    """Return active WordPress hosting containers (user_*_wp_*) from DB."""
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT hosting_id, user_id, container_name
               FROM hostings
               WHERE status NOT IN ('deleted','expired')
                 AND container_name LIKE 'user\\_%%\\_wp\\_%%' ESCAPE '\\'"""
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        release_connection(conn)


def _read_container_logs(container_name: str, since_seconds: int = 90) -> Optional[str]:
    """Fetch recent access logs from a container.

    Strategy (in order):
    1. Try filesystem log files via docker exec tail (Nginx-based images).
    2. Fall back to `docker logs --since={since_seconds}s` (Apache-based images
       write access logs to stdout, captured by Docker's logging driver).
    Returns None if the container is not running or no logs found.
    """
    # Phase 1: filesystem logs (Nginx or Apache with file logging)
    for log_path in ("/var/log/nginx/access.log", "/var/log/apache2/access.log"):
        try:
            r = subprocess.run(
                ["docker", "exec", container_name, "tail", "-n", "500", log_path],
                capture_output=True, text=True, timeout=8,
            )
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout
        except Exception:
            pass

    # Phase 2: docker logs fallback (Apache stdout logging)
    try:
        r = subprocess.run(
            ["docker", "logs", "--since", f"{since_seconds}s", container_name],
            capture_output=True, text=True, timeout=15,
        )
        combined = (r.stdout or "") + (r.stderr or "")
        if combined.strip():
            return combined
    except Exception:
        pass

    return None


def _log_events(rows: list[dict]) -> None:
    """Bulk-insert activity_events (one row per attack hit detected)."""
    if not rows:
        return
    from app.infra.db import get_connection, release_connection
    from datetime import datetime, timezone
    _INSERT = (
        "INSERT INTO activity_events"
        " (user_id, hosting_id, event_type, category, severity, title, message, ip, source, created_at)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'scheduler',%s)"
    )
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        cur = conn.cursor()
        for r in rows:
            cur.execute(_INSERT, (
                r["user_id"], r["hosting_id"], r["event_type"],
                r["category"], r["severity"], r["title"], r["message"],
                r.get("ip"), now,
            ))
        conn.commit()
    except Exception as exc:
        logger.warning("collect_wp_log_attacks: insert failed: %s", exc)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        release_connection(conn)


def collect_wp_log_attacks() -> None:
    """Entry point called by the scheduler every 60 s."""
    try:
        containers = _get_wp_containers()
    except Exception as exc:
        logger.warning("collect_wp_log_attacks: DB query failed: %s", exc)
        return

    if not containers:
        return

    events_to_insert: list[dict] = []

    for c in containers:
        cname    = c["container_name"]
        h_id     = c["hosting_id"]
        u_id     = c["user_id"]

        logs = _read_container_logs(cname)
        if not logs:
            continue

        wp_login_count = 0
        xmlrpc_count   = 0
        last_ip: Optional[str] = None

        for line in logs.splitlines():
            ip_m = _IP_RE.match(line)
            ip   = ip_m.group(1) if ip_m else None

            if _WP_LOGIN_RE.search(line):
                wp_login_count += 1
                last_ip = ip or last_ip
            elif _XMLRPC_RE.search(line):
                xmlrpc_count += 1
                last_ip = ip or last_ip

        if wp_login_count > 0:
            events_to_insert.append({
                "user_id":    u_id,
                "hosting_id": h_id,
                "event_type": "wp_login_failed",
                "category":   "auth",
                "severity":   "warning",
                "title":      f"Intento de login WordPress: {cname}",
                "message":    f"{wp_login_count} POST a wp-login.php detectados en los últimos 90s",
                "ip":         last_ip,
            })

        if xmlrpc_count > 0:
            events_to_insert.append({
                "user_id":    u_id,
                "hosting_id": h_id,
                "event_type": "wp_xmlrpc_attack",
                "category":   "wordpress_auth",
                "severity":   "warning",
                "title":      f"Actividad xmlrpc.php: {cname}",
                "message":    f"{xmlrpc_count} peticiones a xmlrpc.php detectadas en los últimos 90s",
                "ip":         last_ip,
            })

    if events_to_insert:
        _log_events(events_to_insert)
        logger.info(
            "collect_wp_log_attacks: logged %d events across %d containers",
            len(events_to_insert), len(containers),
        )
