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
        except Exception as e:
            # Fallback al fake si falla la inicialización del real (ej. falta API Key)
            print(f"Error initializing OpenAI: {e}")
            return RuleBasedFakeLLM()

    if provider == "anthropic":
        try:
            from app.core.llm.anthropic_llm import AnthropicAdvisoryLLM
            return AnthropicAdvisoryLLM()
        except Exception as e:
            # Fallback al fake si falla la inicialización del real
            print(f"Error initializing Anthropic: {e}")
            return RuleBasedFakeLLM()

    # Fallback seguro para cualquier otro caso
    return RuleBasedFakeLLM()
