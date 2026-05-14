"""
Admin API — Incident Knowledge Base

Endpoints:
  GET  /admin/knowledge/runbooks                    — list all loaded runbooks
  GET  /admin/knowledge/runbooks/{incident_id}      — full runbook detail
  POST /admin/knowledge/match                       — match error text to runbook
  POST /admin/knowledge/safe-actions/validate       — validate action_id against safe/forbidden lists
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.security import require_role

router = APIRouter(prefix="/admin/knowledge", tags=["admin-knowledge"])


class MatchRequest(BaseModel):
    text: str
    incident_type: Optional[str] = None
    hosting_id: Optional[int] = None
    domain: Optional[str] = None


class SafeActionRequest(BaseModel):
    action_id: str
    context: Optional[dict] = None


# ─── Runbooks ──────────────────────────────────────────────────────────────────

@router.get("/runbooks")
def list_runbooks(_: dict = Depends(require_role("admin"))):
    """List all loaded runbooks (frontmatter only, no body)."""
    from app.services.incidents.incident_knowledge_service import get_knowledge_service
    svc = get_knowledge_service()
    svc._ensure_loaded()
    return {
        "runbooks": [
            {
                "incident_id": rb.get("incident_id"),
                "incident_type": rb.get("incident_type"),
                "severity": rb.get("severity"),
                "status": rb.get("status"),
                "validated": rb.get("validated"),
                "auto_repair_allowed": rb.get("auto_repair_allowed"),
                "safe_actions": rb.get("safe_actions") or [],
                "forbidden_actions": rb.get("forbidden_actions") or [],
                "signatures": rb.get("signatures") or [],
            }
            for rb in svc._runbooks.values()
        ],
        "total": len(svc._runbooks),
    }


@router.get("/runbooks/{incident_id}")
def get_runbook(incident_id: str, _: dict = Depends(require_role("admin"))):
    """Return full runbook including body markdown."""
    from app.services.incidents.incident_knowledge_service import get_runbook as _get
    rb = _get(incident_id.upper())
    if not rb:
        raise HTTPException(status_code=404, detail=f"Runbook {incident_id} not found")
    return {
        "incident_id": rb.get("incident_id"),
        "incident_type": rb.get("incident_type"),
        "severity": rb.get("severity"),
        "auto_repair_allowed": rb.get("auto_repair_allowed"),
        "safe_actions": rb.get("safe_actions") or [],
        "forbidden_actions": rb.get("forbidden_actions") or [],
        "signatures": rb.get("signatures") or [],
        "body": rb.get("_body", ""),
        "path": rb.get("_path", ""),
    }


# ─── Matching ──────────────────────────────────────────────────────────────────

@router.post("/match")
def match_incident(req: MatchRequest, _: dict = Depends(require_role("admin"))):
    """
    Match error text / incident_type to the best known runbook.
    Returns matched runbook ID, confidence, safe/forbidden actions.
    """
    from app.services.incidents.incident_knowledge_service import (
        build_incident_context_bundle,
    )
    bundle = build_incident_context_bundle(
        hosting_id=req.hosting_id,
        domain=req.domain,
        error_text=req.text,
        incident_type=req.incident_type,
    )
    return bundle


# ─── Safe actions ──────────────────────────────────────────────────────────────

@router.post("/safe-actions/validate")
def validate_safe_action(req: SafeActionRequest, _: dict = Depends(require_role("admin"))):
    """
    Check whether an action_id is safe to execute.
    Returns allowed=true/false with reason.
    Forbidden actions always return allowed=false.
    """
    from app.services.incidents.safe_actions_validator import can_execute_safe_action
    decision = can_execute_safe_action(req.action_id, req.context)
    return {
        "action_id": decision.action_id,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "requires_dry_run_first": decision.requires_dry_run_first,
        "requires_human_approval": decision.requires_human_approval,
    }


@router.get("/safe-actions")
def list_safe_actions(_: dict = Depends(require_role("admin"))):
    """List all registered safe and forbidden actions."""
    from app.services.incidents.safe_actions_validator import get_validator
    v = get_validator()
    v._ensure_loaded()
    return {
        "safe_actions": list(v._safe.values()),
        "forbidden_actions": list(v._forbidden),
    }
