import os

from app.core.ai_interfaces import AdvisoryLLM
from app.core.llm.fake_llm import RuleBasedFakeLLM


def get_llm() -> AdvisoryLLM:
    """
    Factory para obtener la implementación del LLM según configuración.
    """
    enable_real = os.getenv("ENABLE_REAL_LLM", "false").lower() == "true"

    if not enable_real:
        return RuleBasedFakeLLM()

    provider = os.getenv("LLM_PROVIDER", "openai").lower()

    if provider == "openai":
        try:
            from app.core.llm.openai_llm import OpenAIAdvisoryLLM

            return OpenAIAdvisoryLLM()
        except Exception:
            # Fallback al fake si falla la inicialización del real (ej. falta API Key)
            return RuleBasedFakeLLM()

    # Fallback seguro para cualquier otro caso
    return RuleBasedFakeLLM()
