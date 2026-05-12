"""
Phase 3B: Execution plan safety classifier.

execution_allowed is ALWAYS false in this phase — even for low-risk plans.
Blocked action types must never produce an execution_plan row.
"""
from __future__ import annotations

from typing import TypedDict


class PlanSafetyResult(TypedDict):
    risk_level: str
    execution_allowed: bool          # ALWAYS false
    requires_final_approval: bool    # ALWAYS true
    blocked: bool
    blocked_reason: str


# These action types must never produce an execution plan
_PLAN_BLOCKED: frozenset[str] = frozenset({
    "delete_container",
    "delete_files",
    "modify_dns",
    "drop_database",
    "force_restart_container",
    "modify_docker_compose",
    "resolve_incident_auto",
    "change_traefik",
    "run_shell_command",
    "disable_security",
})

_LOW_RISK: frozenset[str] = frozenset({
    "customer_fix",
    "dependency_fix",
    "branch_correction",
    "monitor",
    "manual_check",
    "site_recovery_monitor",
    "notify_customer",
    "check_credentials",
})

_MEDIUM_RISK: frozenset[str] = frozenset({
    "admin_review",
    "security_review",
    "enable_protection_mode_monitor",
    "escalate_to_admin",
})

_HIGH_RISK: frozenset[str] = frozenset({
    "block_ip_candidate",
    "enable_protection_mode_protect",
    "redeploy_candidate",
    "restart_container_suggestion",
})


def classify_execution_plan(action_type: str) -> PlanSafetyResult:
    """
    Returns safety classification for an execution plan.
    execution_allowed is ALWAYS false (Phase 3B constraint).
    requires_final_approval is ALWAYS true.
    blocked=True means no execution_plan row should be created.
    """
    if action_type in _PLAN_BLOCKED:
        return PlanSafetyResult(
            risk_level="critical",
            execution_allowed=False,
            requires_final_approval=True,
            blocked=True,
            blocked_reason=(
                f"El tipo de acción '{action_type}' está bloqueado por política "
                "y no puede generar un plan de ejecución."
            ),
        )

    if action_type in _LOW_RISK:
        return PlanSafetyResult(
            risk_level="low",
            execution_allowed=False,
            requires_final_approval=True,
            blocked=False,
            blocked_reason="",
        )

    if action_type in _MEDIUM_RISK:
        return PlanSafetyResult(
            risk_level="medium",
            execution_allowed=False,
            requires_final_approval=True,
            blocked=False,
            blocked_reason="",
        )

    if action_type in _HIGH_RISK:
        return PlanSafetyResult(
            risk_level="high",
            execution_allowed=False,
            requires_final_approval=True,
            blocked=False,
            blocked_reason="",
        )

    # Unknown action type — treat as high risk, do not block
    return PlanSafetyResult(
        risk_level="high",
        execution_allowed=False,
        requires_final_approval=True,
        blocked=False,
        blocked_reason="",
    )
