"""
diagnostic_context — builds rich technical context for AI incident diagnosis.

Each source_type gets a dedicated context builder that fetches relevant data
from the DB and structures it into a dict consumed by the LLM prompt builder.
Sensitive values (tokens, passwords, keys) are redacted before leaving this module.
"""
import hashlib
import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = frozenset({
    "token", "password", "secret", "api_key", "apikey", "cookie",
    "authorization", "passwd", "credential", "private_key", "access_key",
    "refresh_token", "access_token",
})
_SENSITIVE_PATTERN = re.compile(
    r"(token|password|secret|api_key|apikey|cookie|authorization|passwd"
    r"|credential|private_key|access_key|refresh_token|access_token)",
    re.IGNORECASE,
)


def redact_sensitive_data(obj: Any) -> Any:
    """Recursively redact sensitive keys in dicts/lists/strings."""
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if _SENSITIVE_PATTERN.fullmatch(k.lower()) else redact_sensitive_data(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact_sensitive_data(item) for item in obj]
    if isinstance(obj, str) and len(obj) > 200:
        return obj[:200] + "…"
    return obj


def compute_context_hash(incident: dict) -> str:
    """SHA256 of the incident fields that define a unique diagnosis context."""
    key = "|".join([
        str(incident.get("incident_id", "")),
        str(incident.get("incident_type", "")),
        str(incident.get("severity", "")),
        str(incident.get("count", "")),
        str(incident.get("last_seen", "")),
        str(incident.get("updated_at", "")),
    ])
    return hashlib.sha256(key.encode()).hexdigest()


# ── Per-source context builders ───────────────────────────────────────────────

def _build_deploy_context(conn, incident: dict) -> dict:
    cur = conn.cursor()
    evidence = incident.get("evidence") or {}
    user_id = incident.get("user_id")
    repo_url = evidence.get("repo_url", "")

    recent_events: list = []
    if user_id and repo_url:
        cur.execute(
            """
            SELECT stage, status, code, message, technical_detail, suggested_fix, evidence, created_at
              FROM deploy_events
             WHERE user_id = %s AND repo_url = %s
             ORDER BY created_at DESC
             LIMIT 5
            """,
            (user_id, repo_url),
        )
        recent_events = [dict(r) for r in cur.fetchall()]

    return {
        "source_type": "deploy",
        "incident_type": incident.get("incident_type"),
        "severity": incident.get("severity"),
        "title": incident.get("title"),
        "count": incident.get("count"),
        "first_seen": str(incident.get("first_seen", "")),
        "last_seen": str(incident.get("last_seen", "")),
        "evidence": redact_sensitive_data(evidence),
        "recent_deploy_events": [redact_sensitive_data(e) for e in recent_events],
    }


def _build_site_context(conn, incident: dict) -> dict:
    cur = conn.cursor()
    hosting_id = incident.get("hosting_id")
    evidence = incident.get("evidence") or {}

    hosting_info: dict = {}
    recent_alerts: list = []

    if hosting_id:
        cur.execute(
            "SELECT name, subdomain, plan, status FROM hostings WHERE hosting_id = %s",
            (hosting_id,),
        )
        row = cur.fetchone()
        if row:
            hosting_info = dict(row)

        cur.execute(
            """
            SELECT alert_type, message, created_at, resolved_at
              FROM site_alerts
             WHERE hosting_id = %s
             ORDER BY created_at DESC
             LIMIT 5
            """,
            (hosting_id,),
        )
        recent_alerts = [dict(r) for r in cur.fetchall()]

    return {
        "source_type": "site",
        "incident_type": incident.get("incident_type"),
        "severity": incident.get("severity"),
        "title": incident.get("title"),
        "count": incident.get("count"),
        "first_seen": str(incident.get("first_seen", "")),
        "last_seen": str(incident.get("last_seen", "")),
        "evidence": redact_sensitive_data(evidence),
        "hosting": hosting_info,
        "recent_alerts": recent_alerts,
    }


def _build_security_context(conn, incident: dict) -> dict:
    cur = conn.cursor()
    hosting_id = incident.get("hosting_id")
    evidence = incident.get("evidence") or {}

    recent_attacks: list = []
    if hosting_id:
        cur.execute(
            """
            SELECT attack_type, severity, ip_address, url, created_at
              FROM wp_attack_log
             WHERE hosting_id = %s
             ORDER BY created_at DESC
             LIMIT 10
            """,
            (hosting_id,),
        )
        rows = cur.fetchall()
        if rows:
            recent_attacks = [dict(r) for r in rows]

    return {
        "source_type": "security",
        "incident_type": incident.get("incident_type"),
        "severity": incident.get("severity"),
        "title": incident.get("title"),
        "count": incident.get("count"),
        "first_seen": str(incident.get("first_seen", "")),
        "last_seen": str(incident.get("last_seen", "")),
        "evidence": redact_sensitive_data(evidence),
        "recent_attacks": recent_attacks,
    }


def _build_system_context(conn, incident: dict) -> dict:
    cur = conn.cursor()
    hosting_id = incident.get("hosting_id")
    evidence = incident.get("evidence") or {}

    resource_summary: dict = {}
    if hosting_id:
        cur.execute(
            """
            SELECT cpu_pct, mem_pct, created_at
              FROM orchestrator_events
             WHERE hosting_id = %s
             ORDER BY created_at DESC
             LIMIT 5
            """,
            (hosting_id,),
        )
        rows = cur.fetchall()
        if rows:
            events = [dict(r) for r in rows]
            resource_summary = {
                "latest_cpu_pct": events[0].get("cpu_pct"),
                "latest_mem_pct": events[0].get("mem_pct"),
                "samples": len(events),
            }

    return {
        "source_type": "system",
        "incident_type": incident.get("incident_type"),
        "severity": incident.get("severity"),
        "title": incident.get("title"),
        "count": incident.get("count"),
        "first_seen": str(incident.get("first_seen", "")),
        "last_seen": str(incident.get("last_seen", "")),
        "evidence": redact_sensitive_data(evidence),
        "resource_summary": resource_summary,
    }


_CONTEXT_BUILDERS = {
    "deploy":   _build_deploy_context,
    "site":     _build_site_context,
    "security": _build_security_context,
    "system":   _build_system_context,
}


def build_incident_context(conn, incident: dict) -> dict:
    """
    Build a rich context dict for an incident.
    Falls back to a minimal context if source_type is unknown.
    """
    source_type = incident.get("source_type", "")
    builder = _CONTEXT_BUILDERS.get(source_type)
    if builder:
        try:
            return builder(conn, incident)
        except Exception as exc:
            logger.warning(
                "build_incident_context(%s, %s) failed: %s",
                source_type, incident.get("incident_id"), exc,
            )
    evidence = incident.get("evidence") or {}
    return {
        "source_type": source_type or "unknown",
        "incident_type": incident.get("incident_type"),
        "severity": incident.get("severity"),
        "title": incident.get("title"),
        "count": incident.get("count"),
        "first_seen": str(incident.get("first_seen", "")),
        "last_seen": str(incident.get("last_seen", "")),
        "evidence": redact_sensitive_data(evidence),
    }
