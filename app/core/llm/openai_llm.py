import os
from typing import Dict, List

from app.core.ai_interfaces import AdvisoryLLM

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore


class OpenAIAdvisoryLLM(AdvisoryLLM):
    """
    LLM real (OpenAI). Read-only. Con timeout y sin side-effects.
    """

    def __init__(self):
        if OpenAI is None:
            raise RuntimeError("OpenAI SDK not installed. Please run 'pip install openai'")

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")

        self.client = OpenAI(api_key=api_key)
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.timeout = int(os.getenv("LLM_TIMEOUT_SECONDS", "5"))

    def generate(self, decision: Dict, context: List[str], debug_context: Optional[Dict] = None) -> str:
        prompt = self._build_prompt(decision, context, debug_context=debug_context)

        # Usando la API v1.0+ de OpenAI
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un asesor técnico experto en hosting. Tu objetivo es explicar diagnósticos y "
                        "riesgos de forma prudente y profesional. NO ejecutes acciones. NO inventes hechos."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            timeout=self.timeout,
        )

        if not response.choices:
            raise RuntimeError("Empty LLM response: no choices returned")
        text = str(response.choices[0].message.content or "").strip()
        if not text:
            raise RuntimeError("Empty LLM response")

        return text

    def _build_prompt(self, decision: Dict, context: List[str], debug_context: Optional[Dict] = None) -> str:
        # Prompt enriquezido con logs si existe debug_context
        debug_section = ""
        if debug_context:
            errors = debug_context.get("logs", {}).get("parsed_errors", [])
            snippet = debug_context.get("logs", {}).get("recent_raw_snippet", "")
            debug_section = f"\nERRORES EN CÓDIGO DETECTADOS (LOGS):\n{errors}\n\nSNIPPET RECIENTE:\n{snippet}\n"

        return f"""
Explica la situación de forma clara y prudente para un cliente.

DECISIÓN DEL SISTEMA (Hechos):
{decision}

CONTEXTO TÉCNICO (Conocimiento curado):
{context}
{debug_section}
Produce una explicación breve, honesta y conservadora. Si ves errores precisos en el código (ej. línea 45 functions.php), menciónalos para que el usuario pueda ir directo a corregirlos. No menciones el formato JSON ni la estructura interna.
"""
