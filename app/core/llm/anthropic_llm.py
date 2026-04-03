import os
from typing import Dict, List

from app.core.ai_interfaces import AdvisoryLLM

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None  # type: ignore


class AnthropicAdvisoryLLM(AdvisoryLLM):
    """
    LLM real (Anthropic Claude). Read-only.
    """

    def __init__(self):
        if Anthropic is None:
            raise RuntimeError("Anthropic SDK not installed. Please run 'pip install anthropic'")

        api_key = os.getenv("CLAUDE_API_KEY")
        if not api_key:
            raise ValueError("CLAUDE_API_KEY environment variable is not set")

        self.client = Anthropic(api_key=api_key)
        self.model = os.getenv("LLM_MODEL", "claude-3-5-sonnet-20240620")
        self.timeout = int(os.getenv("LLM_TIMEOUT_SECONDS", "10"))

    def generate(self, decision: Dict, context: List[str]) -> str:
        prompt = self._build_prompt(decision, context)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Eres un asesor técnico experto en hosting. Tu objetivo es explicar diagnósticos y "
                        "riesgos de forma prudente y profesional. NO ejecutes acciones. NO inventes hechos.\n\n"
                        f"{prompt}"
                    ),
                }
            ],
            timeout=self.timeout,
        )

        # Anthropic v0.3.0+ API
        if not response.content:
            raise RuntimeError("Empty LLM response: no content blocks returned")
        text = response.content[0].text.strip()
        if not text:
            raise RuntimeError("Empty LLM response")

        return text

    def _build_prompt(self, decision: Dict, context: List[str]) -> str:
        return f"""
Explica la situación de forma clara y prudente para un cliente.

DECISIÓN DEL SISTEMA (Hechos):
{decision}

CONTEXTO TÉCNICO (Conocimiento curado):
{context}

Produce una explicación breve, honesta y conservadora. No menciones el formato JSON.
"""
