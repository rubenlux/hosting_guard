"""
Integration tests for the AI Diagnosis system.

TEST 1 — Real error detection
  Simulate realistic log data → verify context, stack extraction,
  system_hint, score_breakdown, and parsed LLM response are all correct.

TEST 2 — Recurring issue detection
  Simulate a first diagnosis, then re-trigger the same error.
  Verify is_recurring=True and that the prompt includes the recurrence warning.

TEST 3 — Cache
  Verify that an identical health snapshot produces the same fingerprint,
  and that when the repository returns a cached result, the LLM is never called.
"""

import asyncio
import json
import logging
import os
import re
from unittest.mock import MagicMock, patch

import pytest

from app.core.health_engine import calculate_health_score
from app.core.log_parser import LogParser
from app.core.llm.context_builder import (
    _summarize_errors,
    build_context,
    build_rag_context,
    detect_recurring_issue,
    extract_stack_info,
)
from app.core.llm.prompt_builder import build_diagnosis_prompt
from app.core.llm.safe_parser import safe_parse_llm
from app.services.hosting.diagnose_service import _build_fingerprint

# ─────────────────────────────────────────────────────────────────────────────
# Shared log fixtures
# ─────────────────────────────────────────────────────────────────────────────

# Python ModuleNotFoundError — docker --timestamps format
IMPORT_ERROR_LOGS = """\
2026-04-12T10:05:28.100000000Z Starting app...
2026-04-12T10:05:30.123456789Z Traceback (most recent call last):
2026-04-12T10:05:30.123456789Z   File "app/main.py", line 15, in <module>
2026-04-12T10:05:30.123456789Z     from app.services.redis_client import get_redis
2026-04-12T10:05:30.200000000Z ModuleNotFoundError: No module named 'redis'
"""

# PHP Fatal error — docker --timestamps format
PHP_ERROR_LOGS = """\
2026-04-12T09:00:00.000000000Z [12-Apr-2026 09:00:00 UTC] PHP Fatal error: Uncaught TypeError: Argument 1 must be string in /var/www/html/index.php on line 42
"""

# External bot probing — should NOT count as application errors
BOT_PROBE_LOGS = """\
2026-04-12T10:00:00.000000000Z 1.2.3.4 - - [12/Apr/2026] "GET /.env HTTP/1.1" 404 0
2026-04-12T10:00:01.000000000Z 1.2.3.4 - - [12/Apr/2026] "GET /wp-admin HTTP/1.1" 404 0
2026-04-12T10:00:02.000000000Z 5.6.7.8 - - [12/Apr/2026] "GET /phpmyadmin HTTP/1.1" 404 0
"""

# Mixed: one real 404 + one bot probe
MIXED_LOGS = """\
2026-04-12T10:00:00.000000000Z 1.2.3.4 - - [12/Apr/2026] "GET /.env HTTP/1.1" 404 0
2026-04-12T10:00:05.000000000Z 9.9.9.9 - - [12/Apr/2026] "GET /api/missing HTTP/1.1" 404 0
"""

# ─────────────────────────────────────────────────────────────────────────────
# TEST 1 — Real error detection
# ─────────────────────────────────────────────────────────────────────────────

class TestRealErrorDetection:

    # ── Log parsing ───────────────────────────────────────────────────────────

    def test_import_error_type_extracted(self):
        """LogParser extracts the exact Python exception class as type."""
        errors = LogParser.parse_logs(IMPORT_ERROR_LOGS)
        assert len(errors) >= 1
        types = [e["type"] for e in errors]
        assert "ModuleNotFoundError" in types

    def test_import_error_source_is_application(self):
        """Python exceptions are always source=application."""
        errors = LogParser.parse_logs(IMPORT_ERROR_LOGS)
        exc = next(e for e in errors if e["type"] == "ModuleNotFoundError")
        assert exc["source"] == "application"

    def test_import_error_message_contains_module(self):
        """Error message includes the missing module name."""
        errors = LogParser.parse_logs(IMPORT_ERROR_LOGS)
        exc = next(e for e in errors if e["type"] == "ModuleNotFoundError")
        assert "redis" in exc["message"].lower()

    def test_php_error_parsed_correctly(self):
        """PHP Fatal error: type=php_error, source=application, file and line extracted."""
        errors = LogParser.parse_logs(PHP_ERROR_LOGS)
        assert len(errors) >= 1
        err = errors[0]
        assert err["type"] == "php_error"
        assert err["source"] == "application"
        assert "index.php" in err["file"]
        assert err["line"] == 42

    def test_php_error_has_timestamp(self):
        """PHP error line has docker timestamp extracted."""
        errors = LogParser.parse_logs(PHP_ERROR_LOGS)
        err = errors[0]
        assert err["ts"] is not None
        assert err["ts"].startswith("2026-04-12")

    def test_bot_probes_classified_as_external(self):
        """All three probe paths → source=external_probe, not application."""
        errors = LogParser.parse_logs(BOT_PROBE_LOGS)
        assert len(errors) == 3
        for err in errors:
            assert err["source"] == "external_probe", f"Expected external_probe, got: {err['source']}"

    def test_mixed_log_source_differentiation(self):
        """Bot probe and real 404 both detected, source differentiated."""
        errors = LogParser.parse_logs(MIXED_LOGS)
        sources = {e["source"] for e in errors}
        assert "external_probe" in sources
        assert "application" in sources

    def test_error_summary_includes_source_annotation(self):
        """_summarize_errors annotates external_probe but not application."""
        errors = LogParser.parse_logs(MIXED_LOGS)
        summary = _summarize_errors(errors)
        assert "[external_probe]" in summary
        # application source is not annotated (it's the default, no noise)
        app_error = next(e for e in errors if e.get("source") == "application")
        # The error itself should appear without source annotation
        assert app_error["file"] in summary or app_error["message"] in summary

    # ── Stack trace extraction ────────────────────────────────────────────────

    def test_stack_info_extracts_deepest_frame(self):
        """extract_stack_info returns the deepest file/line from a traceback."""
        info = extract_stack_info(IMPORT_ERROR_LOGS)
        assert info is not None
        assert "app/main.py" in info["file"]
        assert info["line"] == 15

    def test_stack_info_none_when_no_traceback(self):
        """extract_stack_info returns None for logs without a Python traceback."""
        info = extract_stack_info("Normal log line\nAnother log line\n")
        assert info is None

    # ── System hint ───────────────────────────────────────────────────────────

    def test_system_hint_import_error(self):
        """_detect_system_hint fires the import-specific hint for ModuleNotFoundError."""
        errors = LogParser.parse_logs(IMPORT_ERROR_LOGS)
        ctx = build_context("site", 10.0, 20.0, 80, errors, IMPORT_ERROR_LOGS)
        assert "Import failure" in ctx["system_hint"]
        assert "virtual environment" in ctx["system_hint"]

    def test_system_hint_cpu_pressure(self):
        """High CPU with no errors → CPU pressure hint."""
        ctx = build_context("site", 92.0, 40.0, 70, [], "")
        assert "CPU pressure" in ctx["system_hint"]

    def test_system_hint_stable(self):
        """Clean system → stable hint."""
        ctx = build_context("site", 30.0, 40.0, 95, [], "")
        assert "stable" in ctx["system_hint"].lower()

    # ── Health engine score breakdown ─────────────────────────────────────────

    def test_score_breakdown_cpu_penalty(self):
        """CPU > 85% → -20 in breakdown."""
        result = calculate_health_score({
            "container_status": "running", "cpu": 92.0, "ram": 40.0, "errors": [],
        })
        assert result["score_breakdown"]["cpu_penalty"] == -20

    def test_score_breakdown_ram_penalty(self):
        """RAM > 80% → -15 in breakdown."""
        result = calculate_health_score({
            "container_status": "running", "cpu": 10.0, "ram": 85.0, "errors": [],
        })
        assert result["score_breakdown"]["ram_penalty"] == -15

    def test_score_breakdown_errors_penalty(self):
        """php_fatal → -50 in breakdown."""
        result = calculate_health_score({
            "container_status": "running", "cpu": 10.0, "ram": 10.0,
            "errors": [{"type": "php_fatal", "count": 1}],
        })
        assert result["score_breakdown"]["errors_penalty"] == -50

    def test_score_breakdown_combined(self):
        """CPU + RAM + errors all accumulate correctly."""
        result = calculate_health_score({
            "container_status": "running", "cpu": 92.0, "ram": 85.0,
            "errors": [{"type": "php_fatal", "count": 1}],
        })
        assert result["score"] == 15  # 100 - 20 - 15 - 50
        bd = result["score_breakdown"]
        assert bd["cpu_penalty"] == -20
        assert bd["ram_penalty"] == -15
        assert bd["errors_penalty"] == -50

    def test_external_probe_does_not_affect_score(self):
        """external_probe errors are ignored by the health engine."""
        result = calculate_health_score({
            "container_status": "running", "cpu": 10.0, "ram": 10.0,
            "errors": [{"type": "http_404", "count": 50, "source": "external_probe"}],
        })
        assert result["score"] == 100
        assert "http_404_penalty" not in result["score_breakdown"]

    # ── Alerts in context ─────────────────────────────────────────────────────

    def test_real_alert_appears_in_context(self):
        """Real alert from alert_engine appears formatted in context."""
        errors = LogParser.parse_logs(IMPORT_ERROR_LOGS)
        ctx = build_context(
            "prod-site", 92.0, 85.0, 15, errors, IMPORT_ERROR_LOGS,
            alerts=[{"type": "critical", "message": "Container CPU 92% for 5 minutes"}],
        )
        assert "- [CRITICAL]" in ctx["alerts"]
        assert "CPU 92%" in ctx["alerts"]

    def test_no_alerts_returns_placeholder(self):
        """Empty alerts list → readable 'No recent alerts' placeholder."""
        ctx = build_context("site", 10.0, 20.0, 90, [], "")
        assert ctx["alerts"] == "No recent alerts"

    def test_db_row_alert_format_supported(self):
        """DB row format (level + alert_message keys) is also handled."""
        ctx = build_context(
            "site", 10.0, 20.0, 90, [], "",
            alerts=[{"level": "warning", "alert_message": "RAM above 80%"}],
        )
        assert "[WARNING]" in ctx["alerts"]
        assert "RAM above 80%" in ctx["alerts"]

    # ── Full context fields ───────────────────────────────────────────────────

    def test_full_context_has_all_required_fields(self):
        """build_context emits all fields the prompt template expects."""
        errors = LogParser.parse_logs(IMPORT_ERROR_LOGS)
        result = calculate_health_score({
            "container_status": "running", "cpu": 92.0, "ram": 85.0,
            "errors": [{"type": "php_fatal", "count": 1}],
        })
        ctx = build_context(
            "prod-site", 92.0, 85.0, result["score"], errors, IMPORT_ERROR_LOGS,
            alerts=[{"type": "critical", "message": "CPU spike"}],
            score_breakdown=result["score_breakdown"],
        )
        required = [
            "hosting_name", "environment", "cpu", "ram", "score",
            "errors", "parsed_errors", "logs", "alerts", "system_hint",
            "stack_info", "rag_context", "is_recurring", "score_breakdown",
        ]
        for field in required:
            assert field in ctx, f"Missing field: {field}"

    def test_prompt_contains_score_deductions(self):
        """Score breakdown section appears in the generated prompt."""
        ctx = build_context(
            "site", 92.0, 85.0, 15, [], "",
            score_breakdown={"cpu_penalty": -20, "errors_penalty": -50},
        )
        prompt = build_diagnosis_prompt(ctx)
        assert "Score Deductions" in prompt
        assert "cpu_penalty" in prompt
        assert "-20" in prompt

    # ── LLM response parsing ──────────────────────────────────────────────────

    def test_safe_parser_extracts_all_fields(self):
        """safe_parse_llm handles well-formed JSON and extracts all v2 fields."""
        mock_response = json.dumps({
            "severity":    "critical",
            "failure_type": "import",
            "summary":     "App crash on startup: missing 'redis' package",
            "root_cause":  "ModuleNotFoundError: No module named 'redis' in app/main.py line 15",
            "location":    {"file": "app/main.py", "line": 15, "service": "backend"},
            "evidence":    ["ModuleNotFoundError in logs at 10:05:30Z"],
            "impact":      "Application fails to start — all endpoints return 502",
            "fix":         {"action": "pip install redis", "steps": ["pip install redis", "docker compose up -d --build app"]},
            "confidence":  0.97,
        })
        parsed = safe_parse_llm(mock_response)
        assert parsed["severity"]      == "critical"
        assert parsed["failure_type"]  == "import"
        assert parsed["location"]["file"] == "app/main.py"
        assert parsed["location"]["line"] == 15
        assert len(parsed["fix"]["steps"]) == 2
        assert parsed["confidence"]    == 0.97

    def test_safe_parser_strips_markdown_fences(self):
        """safe_parse_llm strips ```json fences that some LLMs inject."""
        fenced = '```json\n{"severity":"warning","failure_type":"runtime","summary":"test","root_cause":"r","location":{},"evidence":[],"impact":"i","fix":{"action":"a","steps":[]},"confidence":0.5}\n```'
        parsed = safe_parse_llm(fenced)
        assert parsed["severity"] == "warning"

    def test_safe_parser_failure_type_present(self):
        """failure_type field is extracted when present in LLM response."""
        for ft in ("syntax", "import", "runtime", "infra", "unknown"):
            response = json.dumps({
                "severity": "info", "failure_type": ft,
                "summary": "test", "root_cause": "r",
                "location": {}, "evidence": [], "impact": "i",
                "fix": {"action": "a", "steps": []}, "confidence": 0.5,
            })
            parsed = safe_parse_llm(response)
            assert parsed.get("failure_type") == ft, f"failure_type '{ft}' not extracted"


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2 — Recurring error detection
# ─────────────────────────────────────────────────────────────────────────────

class TestRecurringError:
    """
    Simulate a two-round scenario:
      Round 1: ModuleNotFoundError → diagnosed, fix was "pip install redis"
      Round 2: Same error reappears → system must detect recurrence
    """

    HISTORY_ROUND_1 = [
        {
            "severity":     "critical",
            "failure_type": "import",
            "summary":      "App crash on startup: missing 'redis' package",
            "root_cause":   "ModuleNotFoundError: No module named 'redis' at app/main.py:15",
            "fix_action":   "pip install redis && rebuild container",
            "created_at":   "2026-04-10T09:00:00Z",
        }
    ]

    def test_recurrence_detected_by_error_type(self):
        """detect_recurring_issue fires when error type name appears in root_cause."""
        errors = LogParser.parse_logs(IMPORT_ERROR_LOGS)
        assert detect_recurring_issue(errors, self.HISTORY_ROUND_1) is True

    def test_no_recurrence_on_first_occurrence(self):
        """is_recurring=False when history is empty."""
        errors = LogParser.parse_logs(IMPORT_ERROR_LOGS)
        assert detect_recurring_issue(errors, []) is False

    def test_no_recurrence_on_different_error(self):
        """is_recurring=False when error type doesn't match history."""
        php_errors = LogParser.parse_logs(PHP_ERROR_LOGS)
        # History contains ModuleNotFoundError, current error is php_error — no match
        assert detect_recurring_issue(php_errors, self.HISTORY_ROUND_1) is False

    def test_context_is_recurring_flag_set(self):
        """build_context sets is_recurring=True on round 2."""
        errors = LogParser.parse_logs(IMPORT_ERROR_LOGS)
        ctx = build_context(
            "prod-site", 10.0, 20.0, 80, errors, IMPORT_ERROR_LOGS,
            history=self.HISTORY_ROUND_1,
        )
        assert ctx["is_recurring"] is True

    def test_rag_context_includes_previous_fix(self):
        """RAG context in round 2 includes the fix from round 1."""
        errors = LogParser.parse_logs(IMPORT_ERROR_LOGS)
        ctx = build_context(
            "prod-site", 10.0, 20.0, 80, errors, IMPORT_ERROR_LOGS,
            history=self.HISTORY_ROUND_1,
        )
        assert "pip install redis" in ctx["rag_context"]
        assert "CRITICAL" in ctx["rag_context"]
        assert "import" in ctx["rag_context"]  # failure_type from round 1

    def test_prompt_contains_recurrence_warning(self):
        """Prompt includes RECURRING ISSUE DETECTED banner on round 2."""
        errors = LogParser.parse_logs(IMPORT_ERROR_LOGS)
        ctx = build_context(
            "prod-site", 10.0, 20.0, 80, errors, IMPORT_ERROR_LOGS,
            history=self.HISTORY_ROUND_1,
        )
        prompt = build_diagnosis_prompt(ctx)
        assert "RECURRING ISSUE DETECTED" in prompt

    def test_prompt_instructs_explain_prior_fix_failure(self):
        """On recurrence, prompt instructs LLM to explain why prior fix didn't work."""
        errors = LogParser.parse_logs(IMPORT_ERROR_LOGS)
        ctx = build_context(
            "prod-site", 10.0, 20.0, 80, errors, IMPORT_ERROR_LOGS,
            history=self.HISTORY_ROUND_1,
        )
        prompt = build_diagnosis_prompt(ctx)
        assert "prior fix" in prompt.lower()

    def test_prompt_no_recurrence_on_first_occurrence(self):
        """No RECURRING ISSUE banner when history is empty (round 1)."""
        errors = LogParser.parse_logs(IMPORT_ERROR_LOGS)
        ctx = build_context("prod-site", 10.0, 20.0, 80, errors, IMPORT_ERROR_LOGS, history=[])
        prompt = build_diagnosis_prompt(ctx)
        assert "RECURRING ISSUE DETECTED" not in prompt
        assert "No recurrence detected" in prompt


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3 — Cache
# ─────────────────────────────────────────────────────────────────────────────

class TestDiagnosisCache:

    # ── Fingerprint stability ─────────────────────────────────────────────────

    def test_same_state_same_fingerprint(self):
        """Identical snapshot → identical fingerprint (deterministic)."""
        errors = [{"type": "python_exception", "file": "app/main.py", "line": 15}]
        fp1 = _build_fingerprint(30, 92.0, 85.0, errors)
        fp2 = _build_fingerprint(30, 92.0, 85.0, errors)
        assert fp1 == fp2

    def test_different_error_file_different_fingerprint(self):
        """Same error type, different file → different fingerprint (no stale hit)."""
        err_a = [{"type": "python_exception", "source": "application", "file": "app/main.py",  "line": 15}]
        err_b = [{"type": "python_exception", "source": "application", "file": "app/views.py", "line": 99}]
        assert _build_fingerprint(30, 92.0, 85.0, err_a) != _build_fingerprint(30, 92.0, 85.0, err_b)

    def test_different_error_line_different_fingerprint(self):
        """Same file, different line → different fingerprint."""
        err_a = [{"type": "php_error", "source": "application", "file": "index.php", "line": 42}]
        err_b = [{"type": "php_error", "source": "application", "file": "index.php", "line": 99}]
        assert _build_fingerprint(80, 10.0, 10.0, err_a) != _build_fingerprint(80, 10.0, 10.0, err_b)

    def test_cpu_jitter_within_one_decimal_same_fingerprint(self):
        """CPU readings that round to the same 1-decimal value produce the same fingerprint."""
        errors = [{"type": "php_error", "source": "application", "file": "index.php", "line": 42}]
        fp1 = _build_fingerprint(80, 85.00, 60.0, errors)
        fp2 = _build_fingerprint(80, 85.04, 60.0, errors)  # rounds to 85.0
        assert fp1 == fp2

    def test_cpu_jitter_across_decimal_boundary_different_fingerprint(self):
        """CPU change that crosses a 0.1% boundary changes the fingerprint."""
        errors = [{"type": "php_error", "source": "application", "file": "index.php", "line": 42}]
        fp1 = _build_fingerprint(80, 85.04, 60.0, errors)  # rounds to 85.0
        fp2 = _build_fingerprint(80, 85.15, 60.0, errors)  # rounds to 85.2
        assert fp1 != fp2

    def test_fingerprint_is_16_chars(self):
        """Fingerprint is an MD5 hex digest truncated to 16 characters."""
        fp = _build_fingerprint(80, 10.0, 20.0, [])
        assert len(fp) == 16
        assert re.match(r'^[0-9a-f]{16}$', fp)

    def test_empty_errors_use_none_signature(self):
        """No errors → fingerprint uses 'none' as error signature (no crash)."""
        fp = _build_fingerprint(100, 10.0, 20.0, [])
        assert isinstance(fp, str) and len(fp) == 16

    # ── Cache hit: LLM not called ─────────────────────────────────────────────

    def test_cache_hit_skips_llm(self, caplog):
        """
        When get_by_fingerprint returns a cached result, _run_structured_diagnosis
        returns the cached dict immediately and never calls call_llm.

        Strategy: patch both AIDiagnosisRepository.get_by_fingerprint (cache hit)
        and call_llm (LLM call). Assert LLM was NOT called and result is marked cached.
        """
        os.environ["ENABLE_REAL_LLM"] = "true"

        cached_result = {
            "id": 42, "severity": "critical", "failure_type": "import",
            "summary": "Cached: missing redis module",
            "root_cause": "ModuleNotFoundError: No module named 'redis'",
            "evidence": [], "fix_steps": [], "cached": True,
        }

        debug_ctx = {
            "logs": {
                "parsed_errors": [
                    {"type": "ModuleNotFoundError", "file": "app/main.py", "line": 15}
                ],
                "recent_raw_snippet": IMPORT_ERROR_LOGS,
            }
        }

        with patch(
            "app.infra.audit.ai_diagnosis_repository.AIDiagnosisRepository.get_by_fingerprint",
            return_value=cached_result,
        ), patch(
            "app.services.ai_client.call_llm",
        ) as mock_llm, caplog.at_level(
            logging.INFO,
            logger="app.services.hosting.diagnose_service",
        ):
            from app.services.hosting.diagnose_service import _run_structured_diagnosis

            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    _run_structured_diagnosis(
                        hosting_name="prod-site",
                        hosting_id=1,
                        user_id=1,
                        cpu=10.0,
                        ram=20.0,
                        score=80,
                        debug_context=debug_ctx,
                        loop=loop,
                    )
                )
            finally:
                loop.close()

        # LLM must NOT have been called
        mock_llm.assert_not_called()

        # Result is the cached dict
        assert result is not None
        assert result.get("cached") is True
        assert result["summary"] == "Cached: missing redis module"

        # Log must contain cache HIT message
        hit_logs = [r.message for r in caplog.records if "cache HIT" in r.message]
        assert len(hit_logs) >= 1, (
            f"Expected 'Diagnosis cache HIT' in logs. Got: {[r.message for r in caplog.records]}"
        )

        del os.environ["ENABLE_REAL_LLM"]

    def test_cache_miss_calls_llm(self, caplog):
        """
        When get_by_fingerprint returns None (cache miss), call_llm IS called.
        """
        os.environ["ENABLE_REAL_LLM"] = "true"

        llm_response = json.dumps({
            "severity": "critical", "failure_type": "import",
            "summary": "Fresh LLM diagnosis",
            "root_cause": "ModuleNotFoundError",
            "location": {"file": "app/main.py", "line": 15, "service": "backend"},
            "evidence": ["ModuleNotFoundError in logs"],
            "impact": "App fails to start",
            "fix": {"action": "pip install redis", "steps": ["pip install redis"]},
            "confidence": 0.95,
        })

        debug_ctx = {
            "logs": {
                "parsed_errors": [
                    {"type": "ModuleNotFoundError", "file": "app/main.py", "line": 15}
                ],
                "recent_raw_snippet": IMPORT_ERROR_LOGS,
            }
        }

        with patch(
            "app.infra.audit.ai_diagnosis_repository.AIDiagnosisRepository.get_by_fingerprint",
            return_value=None,  # cache MISS
        ), patch(
            "app.infra.audit.ai_diagnosis_repository.AIDiagnosisRepository.get_by_hosting",
            return_value=[],
        ), patch(
            "app.infra.audit.ai_diagnosis_repository.AIDiagnosisRepository.save",
            return_value={"id": 1, "severity": "critical", "failure_type": "import",
                          "summary": "Fresh LLM diagnosis", "cached": False},
        ), patch(
            "app.services.ai_client.call_llm",
            return_value=llm_response,
        ) as mock_llm:
            from app.services.hosting.diagnose_service import _run_structured_diagnosis

            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    _run_structured_diagnosis(
                        hosting_name="prod-site",
                        hosting_id=1,
                        user_id=1,
                        cpu=10.0,
                        ram=20.0,
                        score=80,
                        debug_context=debug_ctx,
                        loop=loop,
                    )
                )
            finally:
                loop.close()

        # LLM MUST have been called exactly once
        mock_llm.assert_called_once()

        assert result is not None
        assert result.get("cached") is not True

        del os.environ["ENABLE_REAL_LLM"]
