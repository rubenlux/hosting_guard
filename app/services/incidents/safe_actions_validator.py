"""
Safe Actions Validator — enforces separation between allowed and forbidden remediations.

Loads safe_actions.yml and forbidden_actions.yml from docs/incidents/remediation/.
"""

from dataclasses import dataclass
from pathlib import Path
import yaml

REMEDIATION_DIR = Path(__file__).parents[3] / "docs" / "incidents" / "remediation"


@dataclass
class Decision:
    allowed: bool
    action_id: str
    reason: str
    requires_dry_run_first: bool = True
    requires_human_approval: bool = False


class SafeActionsValidator:
    def __init__(self):
        self._safe: dict[str, dict] = {}
        self._forbidden: set[str] = set()
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        safe_file = REMEDIATION_DIR / "safe_actions.yml"
        forbidden_file = REMEDIATION_DIR / "forbidden_actions.yml"

        if safe_file.exists():
            data = yaml.safe_load(safe_file.read_text())
            for action in (data.get("safe_actions") or []):
                self._safe[action["id"]] = action

        if forbidden_file.exists():
            data = yaml.safe_load(forbidden_file.read_text())
            for action in (data.get("forbidden_actions") or []):
                self._forbidden.add(action["id"])

        self._loaded = True

    def can_execute_safe_action(self, action_id: str, context: dict | None = None) -> Decision:
        """
        Returns Decision(allowed=True/False) with reason.
        Forbidden actions always return allowed=False regardless of context.
        """
        self._ensure_loaded()

        if action_id in self._forbidden:
            return Decision(
                allowed=False,
                action_id=action_id,
                reason=f"Action '{action_id}' is explicitly forbidden",
                requires_human_approval=True,
            )

        if action_id not in self._safe:
            return Decision(
                allowed=False,
                action_id=action_id,
                reason=f"Action '{action_id}' not found in safe actions registry",
                requires_human_approval=True,
            )

        safe = self._safe[action_id]
        requires_approval = safe.get("requires_human_approval", False)

        return Decision(
            allowed=not requires_approval,
            action_id=action_id,
            reason=safe.get("description", "Safe action approved"),
            requires_dry_run_first=safe.get("requires_dry_run_first", True),
            requires_human_approval=requires_approval,
        )

    def validate_action_list(self, action_ids: list[str], context: dict | None = None) -> list[Decision]:
        return [self.can_execute_safe_action(aid, context) for aid in action_ids]

    def filter_safe(self, action_ids: list[str]) -> list[str]:
        """Return only the actions that are allowed without human approval."""
        return [
            aid for aid in action_ids
            if self.can_execute_safe_action(aid).allowed
        ]


_validator: SafeActionsValidator | None = None


def get_validator() -> SafeActionsValidator:
    global _validator
    if _validator is None:
        _validator = SafeActionsValidator()
    return _validator


def can_execute_safe_action(action_id: str, context: dict | None = None) -> Decision:
    return get_validator().can_execute_safe_action(action_id, context)
