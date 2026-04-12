"""
ai_client — minimal direct LLM call for structured diagnosis.

Intentionally separate from the advisory LLM classes so the diagnosis
path is independent of the existing AIOrchestrator flow.

Only called when ENABLE_REAL_LLM=true and CLAUDE_API_KEY is set.
Returns raw string (caller is responsible for parsing).
"""
import os
import logging

logger = logging.getLogger(__name__)

_MODEL_DEFAULT = "claude-sonnet-4-6"
_MAX_TOKENS    = 1200
_TIMEOUT       = 30  # seconds — diagnosis needs more context than advisory


def call_llm(prompt: str) -> str:
    """
    Make a single synchronous LLM call and return raw response text.

    Raises RuntimeError if the SDK is unavailable or the API call fails.
    Callers should wrap in try/except and degrade gracefully.
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        raise RuntimeError("Anthropic SDK not installed. Run: pip install anthropic")

    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        raise RuntimeError("CLAUDE_API_KEY is not set")

    model = os.getenv("LLM_MODEL", _MODEL_DEFAULT)

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
        timeout=_TIMEOUT,
    )

    if not response.content:
        raise RuntimeError("Empty response from LLM")

    text = response.content[0].text.strip()
    if not text:
        raise RuntimeError("LLM returned empty text")

    return text
