"""Syncs deploy_events → system_incidents (source_type='deploy').

Includes supersede logic: generic codes (build_failed, npm_install_failed,
unknown_deploy_error) are resolved when a specific code is open for the same
user+repo target. Also resolves incidents when a success deploy follows.
"""
import hashlib
import logging
from .incident_deduper import _query, _resolve_incident, _upsert_incident

logger = logging.getLogger(__name__)

_GENERIC_DEPLOY_CODES: frozenset = frozenset({
    "build_failed", "npm_install_failed", "unknown_deploy_error", "invalid_repo_url",
})


def _repo_hash(repo_url: str) -> str:
    return hashlib.sha256(repo_url.encode()).hexdigest()[:12]


def sync_deploy_events(conn) -> dict:
    from app.services.deploy_diagnostics import deploy_severity

    counts: dict = {"created": 0, "updated": 0, "resolved": 0}

    try:
        open_rows = _query(
            conn,
            """
            SELECT de.user_id, de.repo_url, de.branch, de.project_name,
                   de.code, de.stage, de.message, de.suggested_fix, de.evidence,
                   MAX(de.created_at) AS last_seen,
                   COUNT(*)           AS attempt_count
              FROM deploy_events de
             WHERE de.status IN ('failed', 'blocked')
               AND de.created_at > NOW() - INTERVAL '7 days'
               AND NOT EXISTS (
                   SELECT 1 FROM deploy_events ok
                    WHERE ok.user_id  = de.user_id
                      AND ok.repo_url = de.repo_url
                      AND ok.status   = 'success'
                      AND ok.created_at > de.created_at
               )
             GROUP BY de.user_id, de.repo_url, de.branch, de.project_name,
                      de.code, de.stage, de.message, de.suggested_fix, de.evidence
            """,
        )
    except Exception as exc:
        logger.warning("sync_incidents_feed: deploy_events query failed: %s", exc)
        return counts

    # Pre-filter: a generic event that is strictly older than a specific failure
    # for the same target must not be upserted — otherwise the upsert creates a new
    # incident that the post-loop supersede immediately resolves, then the next run
    # creates another one (create→supersede→create loop every 2 minutes).
    target_latest_specific: dict = {}
    for row in open_rows:
        code = row.get("code") or "unknown_deploy_error"
        if code not in _GENERIC_DEPLOY_CODES:
            tgt = (
                row.get("user_id"),
                (row.get("repo_url") or "").strip(),
                row.get("branch") or "",
                row.get("project_name") or "",
            )
            ts = row["last_seen"]
            if tgt not in target_latest_specific or ts > target_latest_specific[tgt]:
                target_latest_specific[tgt] = ts

    effective_rows: list = []
    for row in open_rows:
        code = row.get("code") or "unknown_deploy_error"
        if code in _GENERIC_DEPLOY_CODES:
            tgt = (
                row.get("user_id"),
                (row.get("repo_url") or "").strip(),
                row.get("branch") or "",
                row.get("project_name") or "",
            )
            latest_specific = target_latest_specific.get(tgt)
            if latest_specific is not None and row["last_seen"] < latest_specific:
                logger.debug(
                    "sync_deploy_events: skipping superseded generic code=%s last_seen=%s superseded_at=%s",
                    code, row["last_seen"], latest_specific,
                )
                continue
        effective_rows.append(row)

    seen_keys: set = set()
    for row in effective_rows:
        uid      = row.get("user_id")
        repo_url = row.get("repo_url") or ""
        code     = row.get("code") or "unknown_deploy_error"
        key      = f"deploy:{code}:user:{uid}:repo:{_repo_hash(repo_url)}"
        seen_keys.add(key)

        last_seen = row["last_seen"]
        raw_ev = row.get("evidence") or {}
        evidence: dict = {
            "source":        "deploy_events",
            "code":          code,
            "stage":         row.get("stage"),
            "message":       row.get("message"),
            "suggested_fix": row.get("suggested_fix"),
            "repo_url":      repo_url,
            "branch":        row.get("branch"),
            "project_name":  row.get("project_name"),
            "attempt_count": row["attempt_count"],
            "last_seen":     last_seen.isoformat() if hasattr(last_seen, "isoformat") else str(last_seen),
        }
        if isinstance(raw_ev, dict):
            for field in ("root_directory", "framework", "output_directory", "cleanup_status"):
                if raw_ev.get(field):
                    evidence[field] = raw_ev[field]

        result = _upsert_incident(
            conn,
            source_table="deploy_events",
            source_id=f"{uid}:{_repo_hash(repo_url)}:{code}",
            source_type="deploy",
            correlation_key=key,
            incident_type=code,
            severity=deploy_severity(code),
            hosting_id=None,
            user_id=uid,
            title=f"Deploy failed [{code}]: {row.get('project_name') or repo_url}",
            summary=row.get("message"),
            evidence=evidence,
        )
        counts[result] += 1

    # ── Post-loop: supersede generics + resolve by absence ────────────────────

    try:
        all_open = _query(
            conn,
            """
            SELECT incident_id, correlation_key, incident_type, user_id,
                   evidence->>'repo_url' AS repo_url
              FROM system_incidents
             WHERE source_type = 'deploy' AND status = 'open'
            """,
        )
    except Exception as exc:
        logger.warning("sync_incidents_feed: open-incidents query failed: %s", exc)
        all_open = []

    # Step A: supersede generic codes when a specific code is open for same target.
    # repo_url is stripped so that incidents created from URL-with-space bugs are
    # matched against incidents created from the correctly-normalized URL.
    target_map: dict = {}
    for inc in all_open:
        tgt = (inc.get("user_id"), (inc.get("repo_url") or "").strip())
        target_map.setdefault(tgt, []).append(inc)

    superseded_keys: set = set()
    for _target, _incs in target_map.items():
        _codes = {i["incident_type"] for i in _incs}
        _specific = _codes - _GENERIC_DEPLOY_CODES
        if not _specific:
            continue
        _by = next(iter(_specific))
        for _inc in _incs:
            if _inc["incident_type"] in _GENERIC_DEPLOY_CODES:
                if _resolve_incident(conn, _inc["correlation_key"], {
                    "resolved_by":        "sync_incidents_feed",
                    "resolved_reason":    "superseded_by_specific_deploy_error",
                    "superseded_by_code": _by,
                }):
                    counts["resolved"] += 1
                    superseded_keys.add(_inc["correlation_key"])

    # Step B: resolve by absence.
    # Success only counts as the resolution reason when it is strictly after the
    # most recent failure for that (user_id, repo_url) — prevents an old success
    # from claiming credit for resolving a later failure.
    try:
        _success_targets = {
            (r.get("user_id"), (r.get("repo_url") or "").strip())
            for r in _query(
                conn,
                """
                SELECT DISTINCT d.user_id, d.repo_url
                  FROM deploy_events d
                 WHERE d.status = 'success'
                   AND d.created_at > NOW() - INTERVAL '7 days'
                   AND NOT EXISTS (
                       SELECT 1 FROM deploy_events fail
                        WHERE fail.user_id  = d.user_id
                          AND fail.repo_url = d.repo_url
                          AND fail.status   IN ('failed', 'blocked')
                          AND fail.created_at > d.created_at
                          AND fail.created_at > NOW() - INTERVAL '7 days'
                   )
                """,
            )
        }
    except Exception:
        _success_targets = set()

    for inc in all_open:
        if inc["correlation_key"] in seen_keys:
            continue
        if inc["correlation_key"] in superseded_keys:
            continue
        tgt = (inc.get("user_id"), (inc.get("repo_url") or "").strip())
        reason = "deploy_success" if tgt in _success_targets else "no_recent_failure"
        if _resolve_incident(conn, inc["correlation_key"], {
            "resolved_by":     "sync_incidents_feed",
            "resolved_reason": reason,
        }):
            counts["resolved"] += 1

    return counts
