"""
Remediation policy gate — decides whether an auto-remediation is allowed.

Rules:
- Only types in ALLOWED_AUTO_REMEDIATIONS may be applied automatically.
- Each type must declare reversible=True and a finite ttl_seconds.
- Hosting protection_mode must be 'protect' (or absent, treated as off → reject).
- Cooldown: one remediation per (hosting_id, rule_id, target_value) per COOLDOWN_SECONDS.
- If Redis is unavailable the fallback is ALLOW (fail-open) to avoid false positives.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ── Allowlist ────────────────────────────────────────────────────────────────

ALLOWED_AUTO_REMEDIATIONS: dict[str, dict] = {
    "temporary_ip_block": {
        "reversible": True,
        "ttl_seconds": 900,         # 15 min
        "risk_level": "medium",
        "target_type": "ip",
        "description": "Temporarily block an attacking IP for a hosting",
    },
    "temporary_xmlrpc_block": {
        "reversible": True,
        "ttl_seconds": 3600,        # 1 hour
        "risk_level": "low",
        "target_type": "route",
        "description": "Temporarily disable xmlrpc.php for a hosting",
    },
    "temporary_scanner_block": {
        "reversible": True,
        "ttl_seconds": 3600,
        "risk_level": "low",
        "target_type": "ip",
        "description": "Temporarily block a scanner IP for a hosting",
    },
    "temporary_rate_limit": {
        "reversible": True,
        "ttl_seconds": 600,         # 10 min
        "risk_level": "low",
        "target_type": "ip",
        "description": "Temporary enhanced rate-limit for an IP on wp-login",
    },
}

COOLDOWN_SECONDS = 300  # 5 min between same (hosting_id, rule_id, target_value)

_COOLDOWN_KEY_PREFIX = "hg:remediation_cooldown"


# ── Policy evaluation ────────────────────────────────────────────────────────

@dataclass
class PolicyDecision:
    allowed: bool
    reason: str


def evaluate_remediation_policy(
    *,
    remediation_type: str,
    hosting_id: int,
    rule_id: str,
    target_value: str,
    protection_mode: str,
    redis_client=None,
) -> PolicyDecision:
    """Return PolicyDecision(allowed, reason).

    The caller is responsible for passing the protection_mode string from
    the hosting's protection_mode JSONB field (key 'mode').
    """
    spec = ALLOWED_AUTO_REMEDIATIONS.get(remediation_type)
    if spec is None:
        return PolicyDecision(
            allowed=False,
            reason=f"remediation_type '{remediation_type}' not in allowlist",
        )

    if protection_mode != "protect":
        return PolicyDecision(
            allowed=False,
            reason=f"protection_mode is '{protection_mode}', must be 'protect'",
        )

    if not spec.get("reversible"):
        return PolicyDecision(
            allowed=False,
            reason=f"remediation type '{remediation_type}' is not reversible",
        )

    if not spec.get("ttl_seconds"):
        return PolicyDecision(
            allowed=False,
            reason=f"remediation type '{remediation_type}' has no ttl_seconds",
        )

    # Cooldown check — fail-open if Redis unavailable
    if redis_client is not None:
        try:
            cooldown_key = (
                f"{_COOLDOWN_KEY_PREFIX}:{hosting_id}:{rule_id}:{target_value}"
            )
            if redis_client.exists(cooldown_key):
                return PolicyDecision(
                    allowed=False,
                    reason=f"cooldown active for rule_id='{rule_id}' target='{target_value}'",
                )
        except Exception:
            logger.warning(
                "Redis unavailable during cooldown check — failing open",
                exc_info=True,
            )

    return PolicyDecision(allowed=True, reason="policy approved")


def set_cooldown(
    *,
    hosting_id: int,
    rule_id: str,
    target_value: str,
    redis_client=None,
    ttl: int = COOLDOWN_SECONDS,
) -> None:
    """Set cooldown key in Redis after a remediation is applied."""
    if redis_client is None:
        return
    try:
        key = f"{_COOLDOWN_KEY_PREFIX}:{hosting_id}:{rule_id}:{target_value}"
        redis_client.setex(key, ttl, "1")
    except Exception:
        logger.warning("Redis unavailable — could not set remediation cooldown", exc_info=True)


def get_remediation_spec(remediation_type: str) -> Optional[dict]:
    return ALLOWED_AUTO_REMEDIATIONS.get(remediation_type)
