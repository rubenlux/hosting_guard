"""
Action safety classifier for Phase 3A.

execution_allowed is ALWAYS false in this phase.
Critical actions (delete_container, modify_dns, etc.) are blocked by policy
and must never be inserted into action_recommendations.
"""
from __future__ import annotations

from typing import TypedDict


class SafetyResult(TypedDict):
    risk_level: str
    requires_approval: bool
    execution_allowed: bool
    reason: str
    blocked_by_policy: bool


# Actions that are NEVER stored — policy violation
_POLICY_BLOCKED: frozenset[str] = frozenset({
    "delete_container",
    "delete_files",
    "modify_dns",
    "drop_database",
    "force_restart_container",
    "modify_docker_compose",
    "resolve_incident_auto",
})

_LOW_RISK: frozenset[str] = frozenset({
    "customer_fix",
    "monitor",
    "manual_check",
    "dependency_fix",
    "branch_correction",
    "site_recovery_monitor",
})

_MEDIUM_RISK: frozenset[str] = frozenset({
    "admin_review",
    "security_review",
    "enable_protection_mode_monitor",
    "notify_customer",
    "check_credentials",
})

_HIGH_RISK: frozenset[str] = frozenset({
    "block_ip_candidate",
    "enable_protection_mode_protect",
    "redeploy_candidate",
    "restart_container_suggestion",
    "escalate_to_admin",
})


def classify_action(action_type: str) -> SafetyResult:
    """
    Returns safety classification for an action_type.
    execution_allowed is ALWAYS false (Phase 3A constraint).
    blocked_by_policy=True means the action must not be inserted at all.
    """
    if action_type in _POLICY_BLOCKED:
        return SafetyResult(
            risk_level="critical",
            requires_approval=True,
            execution_allowed=False,
            reason="Acción bloqueada por política — no permitida en Fase 3A",
            blocked_by_policy=True,
        )

    if action_type in _LOW_RISK:
        return SafetyResult(
            risk_level="low",
            requires_approval=True,
            execution_allowed=False,
            reason="Acción informativa — requiere revisión manual",
            blocked_by_policy=False,
        )

    if action_type in _MEDIUM_RISK:
        return SafetyResult(
            risk_level="medium",
            requires_approval=True,
            execution_allowed=False,
            reason="Acción de gestión — requiere aprobación de administrador",
            blocked_by_policy=False,
        )

    if action_type in _HIGH_RISK:
        return SafetyResult(
            risk_level="high",
            requires_approval=True,
            execution_allowed=False,
            reason="Acción de alto impacto — requiere aprobación explícita",
            blocked_by_policy=False,
        )

    # Unknown action type — treat as high risk, do not block
    return SafetyResult(
        risk_level="high",
        requires_approval=True,
        execution_allowed=False,
        reason=f"Tipo de acción desconocido '{action_type}' — clasificado como alto riesgo",
        blocked_by_policy=False,
    )
