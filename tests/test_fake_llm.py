# tests/test_fake_llm.py
from app.core.llm.fake_llm import RuleBasedFakeLLM


def test_fake_llm_generates_explanation_with_context():
    llm = RuleBasedFakeLLM()

    decision = {
        "overall_status": "requires_human",
    }

    context = [
        "Incidentes similares se resolvieron con rollback.",
        "El checkout es un punto crítico en ecommerce.",
    ]

    output = llm.generate(decision, context)

    assert "requiere la intervención de un humano" in output.lower()
    assert "contexto relevante" in output.lower()
    assert "rollback" in output.lower()


def test_fake_llm_generates_explanation_without_context():
    llm = RuleBasedFakeLLM()

    decision = {
        "overall_status": "unknown",
    }

    output = llm.generate(decision, context=[])

    assert "no se pudo determinar" in output.lower()
    assert "estabilidad" in output.lower()
