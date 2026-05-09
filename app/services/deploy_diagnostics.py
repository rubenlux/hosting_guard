"""
Deploy Diagnostic Engine — structured errors and event logging for GitHub Deploy.

DeployError is raised instead of HTTPException for all expected deploy failures.
The endpoint catches it, runs cleanup, records a deploy_event, and returns a
structured JSON response with code/stage/detail/suggested_fix.

deploy_events are read by sync_incidents_feed to surface repeated failures as
system_incidents for the AI Sentinel layer.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Error codes ───────────────────────────────────────────────────────────────

GITHUB_REPO_NOT_FOUND      = "github_repo_not_found"
GITHUB_BRANCH_NOT_FOUND    = "github_branch_not_found"
GITHUB_CLONE_FAILED        = "github_clone_failed"
PACKAGE_JSON_NOT_FOUND     = "package_json_not_found"
MULTIPLE_PROJECT_ROOTS     = "multiple_project_roots_detected"
FRAMEWORK_NOT_SUPPORTED    = "framework_not_supported"
BUILD_SCRIPT_MISSING       = "build_script_missing"
NPM_INSTALL_FAILED         = "npm_install_failed"
NPM_PEER_DEP_FAILED        = "npm_peer_dependency_failed"
BUILD_FAILED               = "build_failed"
OPENSSL_BUILD_FAILED       = "openssl_build_failed"
INDEX_HTML_NOT_FOUND       = "index_html_not_found"
OUTPUT_DIR_MISSING         = "output_directory_missing"
DOCKER_BUILD_FAILED        = "docker_build_failed"
CONTAINER_START_FAILED     = "container_start_failed"
CONTAINER_HEALTH_FAILED    = "container_health_failed"
TRAEFIK_ROUTE_FAILED       = "traefik_route_failed"
SITE_RETURNS_404           = "site_returns_404"
SITE_RETURNS_502           = "site_returns_502"
SITE_RETURNS_503           = "site_returns_503"
DEPLOY_RATE_LIMIT_EXCEEDED = "deploy_rate_limit_exceeded"
UNKNOWN_DEPLOY_ERROR       = "unknown_deploy_error"

# ── Severity (for system_incidents) ──────────────────────────────────────────

_SEVERITY: dict = {
    DEPLOY_RATE_LIMIT_EXCEEDED: "info",
    PACKAGE_JSON_NOT_FOUND:     "warning",
    MULTIPLE_PROJECT_ROOTS:     "warning",
    BUILD_SCRIPT_MISSING:       "warning",
    NPM_INSTALL_FAILED:         "warning",
    NPM_PEER_DEP_FAILED:        "warning",
    BUILD_FAILED:               "warning",
    OPENSSL_BUILD_FAILED:       "warning",
    INDEX_HTML_NOT_FOUND:       "warning",
    OUTPUT_DIR_MISSING:         "warning",
    GITHUB_REPO_NOT_FOUND:      "warning",
    GITHUB_BRANCH_NOT_FOUND:    "warning",
    GITHUB_CLONE_FAILED:        "warning",
    DOCKER_BUILD_FAILED:        "medium",
    CONTAINER_START_FAILED:     "medium",
    CONTAINER_HEALTH_FAILED:    "medium",
    TRAEFIK_ROUTE_FAILED:       "high",
    SITE_RETURNS_502:           "high",
    SITE_RETURNS_503:           "high",
    SITE_RETURNS_404:           "warning",
    UNKNOWN_DEPLOY_ERROR:       "medium",
}


def deploy_severity(code: str) -> str:
    return _SEVERITY.get(code, "warning")


# ── DeployError ───────────────────────────────────────────────────────────────

class DeployError(Exception):
    """
    Raised for any expected deploy failure. Carries all fields needed for a
    structured diagnostic response and for recording in deploy_events.
    """
    def __init__(
        self,
        code: str,
        stage: str,
        detail: str,
        suggested_fix: Optional[str] = None,
        technical_detail: Optional[str] = None,
        evidence: Optional[dict] = None,
        status_code: int = 422,
    ):
        super().__init__(detail)
        self.code             = code
        self.stage            = stage
        self.detail           = detail
        self.suggested_fix    = suggested_fix
        self.technical_detail = technical_detail
        self.evidence         = dict(evidence or {})
        self.status_code      = status_code

    def to_dict(self, request_id: Optional[str] = None) -> dict:
        d: dict = {
            "code":             self.code,
            "stage":            self.stage,
            "detail":           self.detail,
            "suggested_fix":    self.suggested_fix,
            "technical_detail": self.technical_detail,
            "evidence":         self.evidence,
        }
        if request_id:
            d["request_id"] = request_id
        return d


# ── deploy_events DB writer ───────────────────────────────────────────────────

def _repo_hash(repo_url: str) -> str:
    return hashlib.sha256(repo_url.encode()).hexdigest()[:12]


def record_deploy_event(
    *,
    user_id: Optional[int],
    hosting_id: Optional[int] = None,
    repo_url: str,
    branch: str,
    project_name: str,
    stage: str,
    status: str,
    code: Optional[str] = None,
    message: Optional[str] = None,
    technical_detail: Optional[str] = None,
    suggested_fix: Optional[str] = None,
    evidence: Optional[dict] = None,
    cleanup_status: Optional[dict] = None,
) -> None:
    """
    Append a row to deploy_events. Failures are read by sync_incidents_feed.
    Never raises — logs and swallows any DB error so it never blocks the caller.
    """
    from app.infra.db import get_connection, release_connection
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO deploy_events
                (user_id, hosting_id, repo_url, branch, project_name,
                 stage, status, code, message, technical_detail,
                 suggested_fix, evidence, cleanup_status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id, hosting_id, repo_url, branch, project_name,
                stage, status, code, message, technical_detail,
                suggested_fix,
                json.dumps(evidence or {}),
                json.dumps(cleanup_status or {}),
                datetime.now(timezone.utc),
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("record_deploy_event: insert failed: %s", exc)
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
    finally:
        if conn:
            release_connection(conn)
