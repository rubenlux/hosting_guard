"""
build_context — assembles the rich context dict fed into build_diagnosis_prompt.

Keeps the prompt builder dumb (pure string formatter) and the context
builder responsible for shaping / truncating data into prompt-friendly form.

v2 additions:
  - extract_stack_info     : parses Python tracebacks from raw logs
  - build_rag_context      : formats history as structured RAG context
  - detect_recurring_issue : checks if current errors appeared before
  - log truncation to 2000 chars (keeps most-recent window)
  - _detect_system_hint    : now accepts parsed_errors list for richer classification

v3 additions (current):
  - alerts parameter       : real system alerts formatted as readable strings
  - score_breakdown param  : engine penalty breakdown surfaced to LLM
  - _rel_time()            : converts docker ISO timestamps to "N min ago"
  - _summarize_errors()    : includes source + ts per error
"""
import re
from datetime import datetime, timezone
from typing import Any


# ── Log snippet noise filter ─────────────────────────────────────────────────

# HTTP status codes that are completely benign — success, redirect, cache hit.
# These clog the LLM context with irrelevant nginx access log traffic.
_BENIGN_STATUS = re.compile(r'" (200|201|204|206|301|302|304|307|308) ')
# Source map files requested by browser dev-tools — no production impact.
_MAP_404       = re.compile(r'\.map(?:\?[^"]*)?"\s+404')


def _filter_log_snippet(log_str: str) -> str:
    """
    Strip lines the LLM should never diagnose:
      - Benign HTTP responses (200, 304, 301, …) — successful nginx access log entries
      - Source map 404s (.map files) — dev-tool browser requests, no production impact

    Keeps: 5xx errors, application 4xx, Python tracebacks, PHP errors, anything
    that isn't a routine HTTP access log line.

    Without this filter, Claude sees hundreds of '304 0' image/CSS requests and
    draws wrong conclusions about missing assets or deployment failures.
    """
    filtered = []
    for line in log_str.splitlines():
        if _BENIGN_STATUS.search(line):
            continue
        if _MAP_404.search(line):
            continue
        filtered.append(line)

    result = "\n".join(filtered)
    return result if result.strip() else "(No relevant log entries in this window)"


# ── Timestamp helpers ─────────────────────────────────────────────────────────

def _rel_time(ts_str: str | None) -> str | None:
    """
    Convert a docker --timestamps ISO string to a human-readable relative label.
    Returns None when the string is missing or unparseable.
    """
    if not ts_str:
        return None
    try:
        ts   = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        diff = (datetime.now(timezone.utc) - ts).total_seconds()
        if diff < 60:
            return "just now"
        if diff < 3600:
            return f"{int(diff / 60)} min ago"
        return f"{int(diff / 3600)}h ago"
    except Exception:
        return None


# ── Stack trace extraction ────────────────────────────────────────────────────

def extract_stack_info(log_str: str) -> dict | None:
    """
    Extract the deepest Python stack trace frame from raw log text.
    Returns {"file": ..., "line": int} or None if no traceback is found.

    Uses the deepest (last) `File "...", line N` match — that's where
    the exception was actually raised, not an intermediate call site.
    """
    if not log_str:
        return None
    matches = re.findall(r'File "(.+?)", line (\d+)', log_str)
    if not matches:
        return None
    file_path, line_number = matches[-1]
    return {"file": file_path, "line": int(line_number)}


# ── Error summarisation ───────────────────────────────────────────────────────

def _summarize_errors(parsed_errors: list) -> str:
    """
    Convert raw parsed_errors list into sentence form.
    Includes source classification and relative timestamp when available.
    Sentence format is more signal-dense than raw dicts and reduces LLM
    token waste on JSON structural noise.
    """
    if not parsed_errors:
        return "No critical errors detected"

    lines = []
    for e in parsed_errors[:5]:
        parts = [e.get("type", "unknown")]

        # Source annotation — only show when not the default "application"
        source = e.get("source")
        if source and source != "application":
            parts.append(f"[{source}]")

        if e.get("file"):
            parts.append(f"in {e['file']}")
        if e.get("line"):
            parts.append(f"line {e['line']}")
        if e.get("message"):
            parts.append(f"→ {e['message']}")

        ts_label = _rel_time(e.get("ts"))
        if ts_label:
            parts.append(f"({ts_label})")

        lines.append(" ".join(parts))

    return "\n".join(lines)


# ── System hint pre-classification ───────────────────────────────────────────

def _detect_system_hint(parsed_errors: list, cpu: float, ram: float) -> str:
    """
    One-sentence pre-classification that guides the LLM toward the dominant signal.
    Inspects error types directly (not just count) for richer hinting.
    Reduces hallucinations caused by ambiguous multi-signal states.
    """
    error_types = {e.get("type", "") for e in parsed_errors}

    if "SyntaxError" in error_types or "IndentationError" in error_types:
        return "Syntax or indentation error detected — application likely failed to start, check the file/line in the stack trace."
    if "ModuleNotFoundError" in error_types or "ImportError" in error_types:
        return "Import failure — a required module is missing or the virtual environment is broken."
    if parsed_errors:
        return "High probability backend or application failure — focus on error logs and stack trace first."
    if cpu > 80:
        return "Performance degradation under CPU pressure — may be caused by a runaway process or missing database index."
    if ram > 80:
        return "Memory pressure detected — possible memory leak or plan is undersized for current load."
    return "System appears stable — investigate recent deploys or configuration changes if issues were reported."


# ── RAG context formatter ─────────────────────────────────────────────────────

def build_rag_context(history: list) -> str:
    """
    Format previous diagnoses as structured RAG context for the prompt.
    Each entry includes severity, failure_type (if known), summary, root cause,
    applied fix, and date — giving the LLM enough to detect recurring patterns.
    """
    if not history:
        return "No previous diagnoses available."

    lines = []
    for i, h in enumerate(history, 1):
        header_parts = [f"{i}. [{h.get('severity', '?').upper()}]"]
        if h.get("failure_type"):
            header_parts.append(f"({h['failure_type']})")
        header_parts.append(h.get("summary", ""))
        entry = " ".join(header_parts)

        if h.get("root_cause"):
            entry += f"\n   Root cause: {h['root_cause']}"
        if h.get("fix_action"):
            entry += f"\n   Applied fix: {h['fix_action']}"
        if h.get("created_at"):
            entry += f"\n   Date: {str(h['created_at'])[:10]}"

        lines.append(entry)

    return "\n\n".join(lines)


# ── Recurrence detection ──────────────────────────────────────────────────────

def detect_recurring_issue(parsed_errors: list, history: list) -> bool:
    """
    Returns True if any current error type appears in a previous diagnosis.
    Matches error type name against root_cause + summary text of history entries.
    Intentionally conservative: only fires on explicit error type name matches,
    not on vague similarity. False negatives are safer than false positives here.
    """
    if not parsed_errors or not history:
        return False

    current_types = {
        e.get("type", "").lower()
        for e in parsed_errors
        if e.get("type")
    }

    for h in history:
        root    = (h.get("root_cause") or "").lower()
        summary = (h.get("summary") or "").lower()
        for etype in current_types:
            if etype and (etype in root or etype in summary):
                return True

    return False


# ── Alert formatter ───────────────────────────────────────────────────────────

def _format_alerts(alerts: list) -> str:
    """
    Convert a list of alert dicts to a readable bullet list for the prompt.
    Handles both alert_engine format {"type": ..., "message": ...} and
    DB row format {"level": ..., "alert_message": ...}.
    """
    if not alerts:
        return "No recent alerts"

    lines = []
    for a in alerts:
        if not isinstance(a, dict):
            continue
        level = (
            a.get("level")
            or a.get("type")
            or a.get("alert_type")
            or "info"
        ).upper()
        msg = a.get("message") or a.get("alert_message") or ""
        if msg:
            lines.append(f"- [{level}] {msg}")

    return "\n".join(lines) if lines else "No recent alerts"


# ── Score breakdown formatter ─────────────────────────────────────────────────

def _format_score_breakdown(breakdown: dict | None) -> str:
    """
    Format score_breakdown from health_engine as readable lines for the prompt.
    E.g. {"cpu_penalty": -20, "errors_penalty": -50} →
      cpu_penalty: -20
      errors_penalty: -50
    """
    if not breakdown:
        return "No deductions applied (score = 100)"
    return "\n".join(f"  {k}: {v}" for k, v in breakdown.items())


# ── Public API ────────────────────────────────────────────────────────────────

def build_context(
    hosting_name: str,
    cpu: float,
    ram: float,
    score: int,
    parsed_errors: list,
    logs: Any,
    history: list | None = None,
    environment: str = "production",
    alerts: list | None = None,
    score_breakdown: dict | None = None,
) -> dict:
    """
    Returns a context dict ready for build_diagnosis_prompt().

    Args:
        hosting_name:    Human-readable hosting name.
        cpu / ram:       Current resource usage (%).
        score:           Health engine score (0–100).
        parsed_errors:   List of parsed error dicts from debug_context_builder.
        logs:            Raw log snippet (str) or list of log lines.
        history:         List of recent AIDiagnosis dicts (last N diagnoses).
        environment:     Deployment environment label.
        alerts:          Real system alerts (from alert_engine or DB), if any.
        score_breakdown: Penalty breakdown from calculate_health_score(), if available.
    """
    # Normalize logs, strip benign noise lines, then truncate to 2000 most-recent chars
    if isinstance(logs, list):
        log_str = "\n".join(str(line) for line in logs[-20:])
    else:
        log_str = str(logs or "")
    log_str = _filter_log_snippet(log_str)[-2000:]

    # Normalize history — only expose fields useful to the LLM
    clean_history: list[dict] = []
    for h in (history or [])[:3]:
        clean_history.append({
            "summary":      h.get("summary"),
            "root_cause":   h.get("root_cause"),
            "severity":     h.get("severity"),
            "failure_type": h.get("failure_type"),
            "fix_action":   h.get("fix_action"),
            "created_at":   h.get("created_at"),
        })

    # Stack trace: extract deepest Python frame from logs
    stack_info = extract_stack_info(log_str)
    stack_str  = (
        f"File: {stack_info['file']}, Line: {stack_info['line']}"
        if stack_info else None
    )

    # Only pass real application errors to the LLM.
    # dev_noise (source maps, browser requests) and external_probe (bots/scanners)
    # are already excluded from the health score — they must also be excluded here,
    # otherwise Claude diagnoses noise as real issues (the root cause of the bug
    # where Claude reported "missing source map files" as an infra failure).
    actionable_errors = [
        e for e in parsed_errors
        if e.get("source") == "application"
    ]

    # ── Hard guard: no actionable errors AND metrics are clean ──────────────
    # Only fires when there is truly nothing to diagnose: no application errors
    # AND CPU/RAM are within normal range.  If CPU > 80% or RAM > 80% we still
    # want the system_hint to reach the LLM — high resource usage is a real signal.
    # Without this guard, Claude reads benign nginx traffic + empty errors and
    # invents deployment problems — the "hallucination trap" seen in production.
    if not actionable_errors and cpu <= 80 and ram <= 80:
        return {
            "hosting_name":    hosting_name,
            "environment":     environment,
            "cpu":             round(cpu, 1),
            "ram":             round(ram, 1),
            "score":           score,
            "errors":          "No se detectaron errores de aplicación.",
            "parsed_errors":   [],
            "logs":            "(No relevant log entries — only benign traffic detected)",
            "alerts":          _format_alerts(alerts or []),
            "history":         clean_history,
            "system_hint":     "No application errors detected. System appears healthy.",
            "stack_info":      None,
            "rag_context":     build_rag_context(clean_history),
            "is_recurring":    False,
            "score_breakdown": _format_score_breakdown(score_breakdown),
        }

    return {
        "hosting_name":    hosting_name,
        "environment":     environment,
        "cpu":             round(cpu, 1),
        "ram":             round(ram, 1),
        "score":           score,
        # Only actionable errors reach the LLM — no noise, no external probes
        "errors":          _summarize_errors(actionable_errors),
        "parsed_errors":   actionable_errors[:3],
        "logs":            log_str,
        # Real system alerts, formatted as bullet list
        "alerts":          _format_alerts(alerts or []),
        "history":         clean_history,
        # Pre-classification hint uses only actionable errors (no noise)
        "system_hint":     _detect_system_hint(actionable_errors, cpu, ram),
        # Stack trace: deepest Python frame if detected
        "stack_info":      stack_str,
        # Formatted RAG context from previous diagnoses
        "rag_context":     build_rag_context(clean_history),
        # Recurrence flag uses only actionable errors (no noise)
        "is_recurring":    detect_recurring_issue(actionable_errors, clean_history),
        # Score penalty breakdown from health_engine
        "score_breakdown": _format_score_breakdown(score_breakdown),
    }
