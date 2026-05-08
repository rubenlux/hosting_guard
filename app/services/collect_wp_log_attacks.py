"""
WordPress attack log collector.

Runs every 60 s. Reads the last 90 seconds of access logs from every active
WordPress container, detects attack patterns, and inserts activity_events for
aggregate_wp_attacks to aggregate.

actor_type = 'external' on all inserted events so the Activity Timeline never
shows the hosting owner's email as if they performed the attack.

IP classification:
  source_ip      — IP seen in the access log (may be a CDN/proxy)
  client_ip      — same as source_ip (real IP unknown from log alone)
  ip_confidence  — 'direct' | 'proxy_observed' (when source_ip is a Cloudflare range)
  ip_source      — 'remote_addr'
"""
import ipaddress
import json
import logging
import re
import subprocess
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Patterns ──────────────────────────────────────────────────────────────────

_WP_LOGIN_RE = re.compile(r'"POST /wp-login\.php', re.IGNORECASE)
_XMLRPC_RE   = re.compile(r'"/xmlrpc\.php', re.IGNORECASE)

# 302 redirect after POST /wp-login.php → likely successful authentication
_WP_LOGIN_SUCCESS_RE = re.compile(
    r'"POST\s+/wp-login\.php[^"]*"\s+302\b', re.IGNORECASE
)

# Capture the path portion of any /wp-admin/ request
_WP_ADMIN_RE = re.compile(
    r'"(?:GET|POST)\s+(/wp-admin/[^"\s]*)', re.IGNORECASE
)

# Combined log format: IP - user [timestamp] "METHOD path HTTP/x" STATUS size "ref" "ua"
_LOG_COMBINED_RE = re.compile(
    r'^(?P<ip>\S+)\s+\S+\s+\S+\s+'
    r'\[(?P<ts>[^\]]+)\]\s+'
    r'"(?P<method>[A-Z]+)\s+(?P<path>\S+)[^"]*"\s+'
    r'(?P<status>\d{3})\s+\S+'
    r'(?:\s+"[^"]*"\s+"(?P<ua>[^"]*)")?',
)

# Severity for sensitive wp-admin paths
_WP_ADMIN_SEVERITY: dict[str, str] = {
    'plugin-editor.php': 'high',
    'theme-editor.php':  'high',
    'users.php':         'warning',
    'plugins.php':       'warning',
    'admin.php':         'info',
    'index.php':         'info',
}

# ── Cloudflare IP range detection ─────────────────────────────────────────────
# Source: https://www.cloudflare.com/ips-v4 (updated 2026)
_CF_RANGES: list = [
    ipaddress.ip_network(n) for n in (
        "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
        "104.16.0.0/12",   "104.24.0.0/14",   "108.162.192.0/18",
        "131.0.72.0/22",   "141.101.64.0/18",  "162.158.0.0/15",
        "172.64.0.0/13",   "173.245.48.0/20",  "188.114.96.0/20",
        "190.93.240.0/20", "197.234.240.0/22", "198.41.128.0/17",
    )
]


def _is_cloudflare_ip(ip: Optional[str]) -> bool:
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in _CF_RANGES)
    except ValueError:
        return False


def _first_valid_ip(xff: str) -> Optional[str]:
    """Return the first syntactically valid IP from an X-Forwarded-For string."""
    for part in xff.split(","):
        candidate = part.strip()
        try:
            ipaddress.ip_address(candidate)
            return candidate
        except ValueError:
            continue
    return None


def _classify_ip(
    source_ip: Optional[str],
    *,
    cf_connecting_ip: Optional[str] = None,
    x_forwarded_for: Optional[str] = None,
    x_real_ip: Optional[str] = None,
) -> dict:
    """Return IP classification fields for event metadata.

    Priority: CF-Connecting-IP > X-Forwarded-For > X-Real-IP > source_ip.
    client_ip is always equal to source_ip when no forwarding header is
    available — never left None when source_ip is present.
    """
    if cf_connecting_ip:
        return {
            "source_ip":     source_ip,
            "client_ip":     cf_connecting_ip,
            "ip_source":     "cf_connecting_ip",
            "ip_confidence": "forwarded",
        }

    if x_forwarded_for:
        real = _first_valid_ip(x_forwarded_for)
        if real:
            return {
                "source_ip":     source_ip,
                "client_ip":     real,
                "ip_source":     "x_forwarded_for",
                "ip_confidence": "forwarded",
            }

    if x_real_ip:
        return {
            "source_ip":     source_ip,
            "client_ip":     x_real_ip,
            "ip_source":     "x_real_ip",
            "ip_confidence": "forwarded",
        }

    # No forwarding headers available — client_ip = source_ip, never NULL
    if not source_ip:
        return {
            "source_ip":     None,
            "client_ip":     None,
            "ip_source":     "unknown",
            "ip_confidence": "unknown",
        }

    confidence = "proxy_observed" if _is_cloudflare_ip(source_ip) else "direct"
    return {
        "source_ip":     source_ip,
        "client_ip":     source_ip,
        "ip_source":     "remote_addr",
        "ip_confidence": confidence,
    }


# ── Log parsing ───────────────────────────────────────────────────────────────

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


def _wp_admin_severity(path: str) -> str:
    """Return severity for a /wp-admin/ path based on its filename."""
    filename = path.rstrip("/").rsplit("/", 1)[-1].lower()
    return _WP_ADMIN_SEVERITY.get(filename, "info")


# ── DB helpers ────────────────────────────────────────────────────────────────

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
      'docker_logs' — fallback via docker logs --since (Apache stdout)
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


# ── Main entry point ──────────────────────────────────────────────────────────

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
        login_success  = 0
        last_ip: Optional[str] = None
        last_ua: Optional[str] = None
        ip_info: dict          = {}

        # wp-admin: deduplicate by (normalized_path, ip) within this run
        admin_seen: dict[tuple, dict] = {}

        for line in logs.splitlines():
            parsed = _parse_log_line(line)
            ip = parsed.get("ip")
            ua = parsed.get("ua")

            # wp-admin detection (independent of login/xmlrpc checks)
            m_admin = _WP_ADMIN_RE.search(line)
            if m_admin:
                path_raw = m_admin.group(1)
                path = path_raw.split("?")[0].rstrip("/").lower() or "/wp-admin/"
                key = (path, ip or "")
                if key not in admin_seen:
                    admin_seen[key] = {
                        "count":    0,
                        "ua":       ua,
                        "severity": _wp_admin_severity(path),
                        "ip":       ip,
                    }
                admin_seen[key]["count"] += 1

            if _WP_LOGIN_SUCCESS_RE.search(line):
                login_success += 1
                last_ip = ip or last_ip
                last_ua = ua or last_ua
                ip_info = _classify_ip(ip or last_ip)
            elif _WP_LOGIN_RE.search(line):
                wp_login_count += 1
                last_ip = ip or last_ip
                last_ua = ua or last_ua
                ip_info = _classify_ip(ip or last_ip)
            elif _XMLRPC_RE.search(line):
                xmlrpc_count += 1
                last_ip = ip or last_ip
                last_ua = ua or last_ua
                ip_info = _classify_ip(ip or last_ip)

        if not ip_info:
            ip_info = _classify_ip(last_ip)

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
                **ip_info,
            }
            if last_ua:
                meta["user_agent"] = last_ua

            events_to_insert.append({
                "user_id":    u_id,
                "hosting_id": h_id,
                "event_type": "wp_login_failed",
                "category":   "auth",
                "severity":   "warning",
                "title":      f"Intento de login WordPress: {cname}",
                "message":    (
                    f"{wp_login_count} POST a wp-login.php detectados "
                    f"en los últimos 90s"
                ),
                "ip":         ip_info.get("client_ip") or last_ip,
                "user_agent": last_ua,
                "metadata":   meta,
            })

        if login_success > 0:
            ls_ip = _classify_ip(last_ip)
            meta_ls: dict = {
                "container_name": cname,
                "hosting_id":     h_id,
                "source":         log_source,
                "detected_by":    "collect_wp_log_attacks",
                "path":           "/wp-login.php",
                "status_code":    "302",
                "classification": "possible_success",
                "login_count":    login_success,
                "observed_at":    observed_at,
                **ls_ip,
            }
            if last_ua:
                meta_ls["user_agent"] = last_ua

            events_to_insert.append({
                "user_id":    u_id,
                "hosting_id": h_id,
                "event_type": "wp_login_success",
                "category":   "auth",
                "severity":   "info",
                "title":      f"Posible login exitoso WordPress: {cname}",
                "message":    (
                    f"{login_success} POST a wp-login.php con redirect 302 "
                    f"en {cname}"
                ),
                "ip":         ls_ip.get("client_ip") or last_ip,
                "user_agent": last_ua,
                "metadata":   meta_ls,
            })

        if xmlrpc_count > 0:
            meta_x: dict = {
                "container_name": cname,
                "hosting_id":     h_id,
                "source":         log_source,
                "detected_by":    "collect_wp_log_attacks",
                "path":           "/xmlrpc.php",
                "attack_count":   xmlrpc_count,
                "observed_at":    observed_at,
                **ip_info,
            }
            if last_ua:
                meta_x["user_agent"] = last_ua

            events_to_insert.append({
                "user_id":    u_id,
                "hosting_id": h_id,
                "event_type": "wp_xmlrpc_attack",
                "category":   "wordpress_auth",
                "severity":   "warning",
                "title":      f"Actividad xmlrpc.php: {cname}",
                "message":    (
                    f"{xmlrpc_count} peticiones a xmlrpc.php detectadas "
                    f"en los últimos 90s"
                ),
                "ip":         ip_info.get("client_ip") or last_ip,
                "user_agent": last_ua,
                "metadata":   meta_x,
            })

        # One event per unique (path, ip) combo in /wp-admin/
        for (path, ip), info in admin_seen.items():
            adm_ip = _classify_ip(ip or None)
            meta_adm: dict = {
                "container_name": cname,
                "hosting_id":     h_id,
                "source":         log_source,
                "detected_by":    "collect_wp_log_attacks",
                "path":           path,
                "access_count":   info["count"],
                "observed_at":    observed_at,
                **adm_ip,
            }
            if info.get("ua"):
                meta_adm["user_agent"] = info["ua"]

            filename = path.rstrip("/").rsplit("/", 1)[-1] or "index"
            events_to_insert.append({
                "user_id":    u_id,
                "hosting_id": h_id,
                "event_type": "wp_admin_access",
                "category":   "auth",
                "severity":   info["severity"],
                "title":      f"Acceso wp-admin ({filename}): {cname}",
                "message":    (
                    f"{info['count']} acceso(s) a {path} en {cname}"
                ),
                "ip":         adm_ip.get("client_ip") or ip or None,
                "user_agent": info.get("ua"),
                "metadata":   meta_adm,
            })

    if events_to_insert:
        _log_events(events_to_insert)
        logger.info(
            "collect_wp_log_attacks: logged %d events across %d containers",
            len(events_to_insert), len(containers),
        )
