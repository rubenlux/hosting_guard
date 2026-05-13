"""
Auto-remediation rules for HostingGuard Phase 4A.

Each rule is a dataclass that decides whether a security event warrants
automatic remediation and, if so, what type/parameters to use.

Rules fire ONLY when protection_mode == 'protect'.
All types must be in ALLOWED_AUTO_REMEDIATIONS.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from app.services.security.remediation_policy import ALLOWED_AUTO_REMEDIATIONS

logger = logging.getLogger(__name__)


@dataclass
class RemediationDecision:
    should_remediate: bool
    remediation_type: Optional[str] = None
    target_type: Optional[str] = None
    target_value: Optional[str] = None
    reason: Optional[str] = None
    ttl_override: Optional[int] = None  # overrides spec default if set


# ── Rule 1: wp_login brute-force ─────────────────────────────────────────────

BRUTE_FORCE_THRESHOLD = 5  # attempts in event.count

def rule_wp_login_brute_force(event: dict) -> RemediationDecision:
    """Temporary IP block for wp-login brute-force."""
    if event.get("event_type") != "brute_force_wp_login":
        return RemediationDecision(should_remediate=False)

    ip = event.get("ip")
    if not ip:
        return RemediationDecision(should_remediate=False)

    count = event.get("count", 1)
    if count < BRUTE_FORCE_THRESHOLD:
        return RemediationDecision(should_remediate=False)

    return RemediationDecision(
        should_remediate=True,
        remediation_type="temporary_ip_block",
        target_type="ip",
        target_value=ip,
        reason=f"brute_force_wp_login: {count} intentos desde {ip}",
    )


# ── Rule 2: xmlrpc abuse ──────────────────────────────────────────────────────

def rule_xmlrpc_abuse(event: dict) -> RemediationDecision:
    """Temporarily disable xmlrpc.php for a hosting under attack."""
    if event.get("event_type") != "xmlrpc_abuse":
        return RemediationDecision(should_remediate=False)

    hosting_id = event.get("hosting_id")
    if not hosting_id:
        return RemediationDecision(should_remediate=False)

    ip = event.get("ip", "xmlrpc_route")
    return RemediationDecision(
        should_remediate=True,
        remediation_type="temporary_xmlrpc_block",
        target_type="route",
        target_value="xmlrpc",
        reason=f"xmlrpc_abuse desde {ip}",
    )


# ── Rule 3: scanner / path traversal ────────────────────────────────────────

SCANNER_THRESHOLD = 3  # distinct scanner path hits

def rule_scanner_block(event: dict) -> RemediationDecision:
    """Temporarily block a scanner IP for a hosting."""
    if event.get("event_type") not in ("scanner_detected", "path_traversal"):
        return RemediationDecision(should_remediate=False)

    ip = event.get("ip")
    if not ip:
        return RemediationDecision(should_remediate=False)

    count = event.get("count", 1)
    if count < SCANNER_THRESHOLD:
        return RemediationDecision(should_remediate=False)

    return RemediationDecision(
        should_remediate=True,
        remediation_type="temporary_scanner_block",
        target_type="ip",
        target_value=ip,
        reason=f"scanner_detected: {count} hits de rutas de exploración desde {ip}",
    )


# ── Rule 4: rate limit burst on wp-login ─────────────────────────────────────

RATE_LIMIT_THRESHOLD = 10  # requests triggering enhanced rate-limit

def rule_rate_limit(event: dict) -> RemediationDecision:
    """Enhanced temporary rate-limit for an IP hammering wp-login."""
    if event.get("event_type") != "rate_limit_exceeded":
        return RemediationDecision(should_remediate=False)

    ip = event.get("ip")
    if not ip:
        return RemediationDecision(should_remediate=False)

    count = event.get("count", 1)
    if count < RATE_LIMIT_THRESHOLD:
        return RemediationDecision(should_remediate=False)

    return RemediationDecision(
        should_remediate=True,
        remediation_type="temporary_rate_limit",
        target_type="ip",
        target_value=ip,
        reason=f"rate_limit_exceeded: {count} requests desde {ip}",
        ttl_override=600,
    )


# ── Registry ──────────────────────────────────────────────────────────────────

RULES = [
    ("wp_login_brute_force",  rule_wp_login_brute_force),
    ("xmlrpc_abuse",          rule_xmlrpc_abuse),
    ("scanner_block",         rule_scanner_block),
    ("rate_limit",            rule_rate_limit),
]


def evaluate_all_rules(event: dict) -> list[tuple[str, RemediationDecision]]:
    """Evaluate all rules against a security event.

    Returns list of (rule_id, RemediationDecision) for rules that fire.
    """
    decisions = []
    for rule_id, rule_fn in RULES:
        try:
            decision = rule_fn(event)
            if decision.should_remediate:
                decisions.append((rule_id, decision))
        except Exception:
            logger.exception("auto_remediation_rules: rule '%s' raised unexpectedly", rule_id)
    return decisions
