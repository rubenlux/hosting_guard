"""
Tests E2E ecommerce — verifica el contrato completo de la API sin DB real.
La persistencia en PostgreSQL se verifica en CI/producción con DB real.
"""


def test_e2e_ecommerce_with_ai_and_audit(client):
    headers = {"X-API-Key": "key-client-1"}
    payload = {
        "hosting_type": "vps",
        "project_type": "ecommerce",
        "symptoms": ["checkout_error"],
        "recent_changes": ["deploy"],
        "estimated_impact": "high",
    }

    response = client.post("/decision", json=payload, headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert data["tenant_id"] == "tenant_1"
    assert data["overall_status"] in {"requires_human", "blocked"}
    assert "advisory" in data

    advisory = data["advisory"]
    assert advisory["requires_human_attention"] is True
    assert "summary" in advisory

    # IA habilitada via fixture `client`
    assert "llm_explanation" in advisory
    assert "context_used" in advisory
    assert isinstance(advisory["context_used"], list)


def test_e2e_invalid_tenant_rejected(client):
    headers = {"X-API-Key": "invalid-key"}

    response = client.post("/decision", json={}, headers=headers)
    assert response.status_code == 401


def test_e2e_ai_flag_off(monkeypatch, client):
    # Forzamos flag OFF para este caso
    monkeypatch.setattr("app.api.main.ENABLE_AI_ADVISORY", False)

    headers = {"X-API-Key": "key-client-1"}
    payload = {
        "hosting_type": "shared",
        "project_type": "wordpress",
        "symptoms": ["error_500"],
        "recent_changes": ["plugin_update"],
        "estimated_impact": "medium",
    }

    response = client.post("/decision", json=payload, headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert "advisory" in data
    # Con flag OFF, no debe haber enriquecimiento
    assert data["advisory"].get("llm_explanation") is None
