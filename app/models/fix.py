"""
FixProposal — structured remediation proposal generated from a diagnosis.
FixExecutionResult — outcome of running a proposed fix.

Design rules:
  - can_auto_fix=False on syntax/import failures: those need a developer.
  - risk_level drives the UI: "low" can be applied with one click;
    "medium" shows a confirmation; "high" is display-only (no apply button).
  - commands / rollback_commands are validated against the execution
    whitelist before any subprocess call — the model never bypasses it.
"""
from typing import List, Optional
from pydantic import BaseModel


class FixProposal(BaseModel):
    fingerprint: str          # links to the diagnosis snapshot
    hosting_id: int
    container_name: str
    failure_type: str         # mirrors AI diagnosis failure_type
    risk_level: str           # low | medium | high | none
    can_auto_fix: bool        # False → manual only, no apply button
    title: str                # short human label, e.g. "Reiniciar contenedor"
    description: str          # one-sentence explanation for the user
    action: str               # canonical action id: nginx_reload | docker_restart | docker_start | manual
    commands: List[str]       # ordered shell tokens — only meaningful when can_auto_fix=True
    rollback_commands: List[str]  # tokens to undo if execution fails
    estimated_downtime: str   # "0s" | "5–10s" | "30–60s" | "n/a"


class FixExecutionResult(BaseModel):
    success: bool
    action: str
    stdout: str = ""
    stderr: str = ""
    rolled_back: bool = False
    error: Optional[str] = None
