"""
WordPress attack log collector.

Runs every 60 s. Reads the last 90 seconds of access logs from every active
WordPress container, detects wp-login.php POST and xmlrpc.php requests, and
inserts activity_events for aggregate_wp_attacks to aggregate.

actor_type = 'external' on all inserted events so the Activity Timeline never
shows the hosting owner's email as if they performed the attack.
"""
import json
import logging
import re
import subprocess
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_WP_LOGIN_RE = re.compile(r'"POST /wp-login\.php', re.IGNORECASE)
# Match ALL requests to xmlrpc.php (including 403s already blocked by hardening)
_XMLRPC_RE   = re.compile(r'"/xmlrpc\.php', re.IGNORECASE)

# Combined log format: IP - user [timestamp] "METHOD path HTTP/x" STATUS size "ref" "ua"
_LOG_COMBINED_RE = re.compile(
    r'^(?P<ip>\S+)\s+\S+\s+\S+\s+'
    r'\[(?P<ts>[^\]]+)\]\s+'
    r'"(?P<method>[A-Z]+)\s+(?P<path>\S+)[^"]*"\s+'
    r'(?P<status>\d{3})\s+\S+'
    r'(?:\s+"[^"]*"\s+"(?P<ua>[^"]*)")?',
)


def _parse_log_line(line: str) -> dict:
    """Parse a combined log line. Returns a dict with available fields."""
    m = _LOG_COMBINED_RE.match(line)
    if not m:
        ip_m = re.match(r'^(\S+)', line)
        return {"ip": ip_m.group(1) if ip_m else None}
    return {
        "ip":     m.group("ip"),
        "method": m.group("method"),
        "path":   m.group("path"),
        "status": m.group("status"),
        "ua":     m.group("ua"),
        "ts":     m.group("ts"),
    }


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


def _read_container_logs(
    container_name: str, since_seconds: int = 90
) -> tuple[Optional[str], str]:
    """Fetch recent access logs from a container.

    Returns (log_text, source_label) where source_label is one of:
      'access_log'  — read from filesystem via docker exec
      'docker_logs' — fallback via docker logs --since
      'none'        — no logs found
    """
    for log_path in ("/var/log/nginx/access.log", "/var/log/apache2/access.log"):
        try:
            r = subprocess.run(
                ["docker", "exec", container_name, "tail", "-n", "500", log_path],
                capture_output=True, text=True, timeout=8,
            )
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout, "access_log"
        except Exception:
            pass

    try:
        r = subprocess.run(
            ["docker", "logs", "--since", f"{since_seconds}s", container_name],
            capture_output=True, text=True, timeout=15,
        )
        combined = (r.stdout or "") + (r.stderr or "")
        if combined.strip():
            return combined, "docker_logs"
    except Exception:
        pass

    return None, "none"


def _log_events(rows: list[dict]) -> None:
    """Bulk-insert activity_events with actor_type='external'."""
    if not rows:
        return
    _INSERT = (
        "INSERT INTO activity_events"
        " (user_id, hosting_id, event_type, category, severity, title,"
        "  message, ip, user_agent, actor_type, metadata, source, created_at)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'external',%s::jsonb,'scheduler',%s)"
    )
    now = datetime.now(timezone.utc).isoformat()
    from app.infra.db import get_connection, release_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        for r in rows:
            cur.execute(_INSERT, (
                r["user_id"], r["hosting_id"], r["event_type"],
                r["category"], r["severity"], r["title"], r["message"],
                r.get("ip"), r.get("user_agent"),
                json.dumps(r.get("metadata") or {}),
                now,
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
        cname = c["container_name"]
        h_id  = c["hosting_id"]
        u_id  = c["user_id"]

        logs, log_source = _read_container_logs(cname)
        if not logs:
            continue

        wp_login_count = 0
        xmlrpc_count   = 0
        last_ip: Optional[str]  = None
        last_ua: Optional[str]  = None

        for line in logs.splitlines():
            parsed = _parse_log_line(line)
            ip = parsed.get("ip")
            ua = parsed.get("ua")

            if _WP_LOGIN_RE.search(line):
                wp_login_count += 1
                last_ip = ip or last_ip
                last_ua = ua or last_ua
            elif _XMLRPC_RE.search(line):
                xmlrpc_count += 1
                last_ip = ip or last_ip
                last_ua = ua or last_ua

        observed_at = datetime.now(timezone.utc).isoformat()

        if wp_login_count > 0:
            meta: dict = {
                "container_name": cname,
                "hosting_id":     h_id,
                "source":         log_source,
                "detected_by":    "collect_wp_log_attacks",
                "path":           "/wp-login.php",
                "method":         "POST",
                "attack_count":   wp_login_count,
                "observed_at":    observed_at,
            }
            if last_ip:
                meta["source_ip"] = last_ip
            if last_ua:
                meta["user_agent"] = last_ua

            events_to_insert.append({
                "user_id":    u_id,
                "hosting_id": h_id,
                "event_type": "wp_login_failed",
                "category":   "auth",
                "severity":   "warning",
                "title":      f"Intento de login WordPress: {cname}",
                "message":    f"{wp_login_count} POST a wp-login.php detectados en los últimos 90s",
                "ip":         last_ip,
                "user_agent": last_ua,
                "metadata":   meta,
            })

        if xmlrpc_count > 0:
            meta = {
                "container_name": cname,
                "hosting_id":     h_id,
                "source":         log_source,
                "detected_by":    "collect_wp_log_attacks",
                "path":           "/xmlrpc.php",
                "attack_count":   xmlrpc_count,
                "observed_at":    observed_at,
            }
            if last_ip:
                meta["source_ip"] = last_ip
            if last_ua:
                meta["user_agent"] = last_ua

            events_to_insert.append({
                "user_id":    u_id,
                "hosting_id": h_id,
                "event_type": "wp_xmlrpc_attack",
                "category":   "wordpress_auth",
                "severity":   "warning",
                "title":      f"Actividad xmlrpc.php: {cname}",
                "message":    f"{xmlrpc_count} peticiones a xmlrpc.php detectadas en los últimos 90s",
                "ip":         last_ip,
                "user_agent": last_ua,
                "metadata":   meta,
            })

    if events_to_insert:
        _log_events(events_to_insert)
        logger.info(
            "collect_wp_log_attacks: logged %d events across %d containers",
            len(events_to_insert), len(containers),
        )
