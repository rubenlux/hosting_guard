"""
safe_parse_llm — fault-tolerant JSON parser for LLM responses.

Claude occasionally wraps JSON in markdown fences or adds explanatory text.
This module strips that noise and falls back gracefully on parse failure.
"""
import json
import re


def safe_parse_llm(response: str) -> dict:
    """
    Parse a JSON response from the LLM.

    Handles:
    - Clean JSON strings
    - JSON wrapped in ```json ... ``` fences
    - JSON preceded or followed by explanation text
    - Completely malformed responses (returns degraded fallback)
    """
    if not response:
        return _fallback("Empty LLM response", response)

    text = response.strip()

    # Strip markdown code fences if present
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fenced:
        text = fenced.group(1).strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting the first {...} block
    brace = re.search(r"\{[\s\S]+\}", text)
    if brace:
        try:
            return json.loads(brace.group(0))
        except json.JSONDecodeError:
            pass

    return _fallback("LLM response could not be parsed as JSON", response)


def _fallback(reason: str, raw: str) -> dict:
    return {
        "severity": "warning",
        "summary": reason,
        "root_cause": (raw[:400] if raw else "No response"),
        "location": {"file": None, "line": None, "service": "unknown"},
        "evidence": [],
        "impact": "Diagnosis unavailable — review raw logs manually.",
        "fix": {"action": "Inspect container logs directly.", "steps": []},
        "confidence": 0.1,
    }
