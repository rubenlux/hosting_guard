import logging
import os

from app.core.ai_interfaces import AdvisoryLLM
from app.core.llm.fake_llm import RuleBasedFakeLLM

logger = logging.getLogger(__name__)


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
            logger.error(
                "Failed to initialize OpenAI LLM — falling back to RuleBasedFakeLLM. "
                "Check OPENAI_API_KEY and openai SDK installation.",
                exc_info=True,
            )
            return RuleBasedFakeLLM()

    if provider == "anthropic":
        try:
            from app.core.llm.anthropic_llm import AnthropicAdvisoryLLM
            return AnthropicAdvisoryLLM()
        except Exception:
            # Fallback al fake si falla la inicialización del real
            logger.error(
                "Failed to initialize Anthropic LLM — falling back to RuleBasedFakeLLM. "
                "Check CLAUDE_API_KEY and anthropic SDK installation.",
                exc_info=True,
            )
            return RuleBasedFakeLLM()

    # Provider desconocido — advertencia explícita antes del fallback
    logger.warning(
        "Unknown LLM_PROVIDER=%r — falling back to RuleBasedFakeLLM. "
        "Supported providers: 'openai', 'anthropic'.",
        provider,
    )
    return RuleBasedFakeLLM()
