from app.core.llm.factory import get_llm
from app.core.llm.fake_llm import RuleBasedFakeLLM


def test_llm_factory_returns_fake_by_default(monkeypatch):
    monkeypatch.setenv("ENABLE_REAL_LLM", "false")
    llm = get_llm()
    assert isinstance(llm, RuleBasedFakeLLM)


def test_llm_factory_returns_fake_if_flag_true_but_no_api_key(monkeypatch):
    monkeypatch.setenv("ENABLE_REAL_LLM", "true")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    llm = get_llm()
    # Debería haber hecho fallback a RuleBasedFakeLLM
    assert isinstance(llm, RuleBasedFakeLLM)
