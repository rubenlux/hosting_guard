# tests/test_e2e_ecommerce.py
import sqlite3

from app.infra.audit import sqlite as audit_sqlite


def test_e2e_ecommerce_with_ai_and_audit(client):
    headers = {"X-API-Key": "key-client-1"}

    # Usamos el path del módulo para asegurar que vemos el monkeypatch de conftest
    db_path = audit_sqlite.DB_PATH

    payload = {
        "hosting_type": "vps",
        "project_type": "ecommerce",
        "symptoms": ["checkout_error"],
        "recent_changes": ["deploy"],
        "estimated_impact": "high",
    }

    # 1. Llamada a la API
    response = client.post("/decision", json=payload, headers=headers)
    assert response.status_code == 200

    data = response.json()

    # 2. Verificar API / contrato
    assert data["tenant_id"] == "tenant_1"
    assert data["overall_status"] in {"requires_human", "blocked"}
    assert "advisory" in data

    # 3. Verificar Advisory
    advisory = data["advisory"]
    assert advisory["requires_human_attention"] is True
    assert "summary" in advisory

    # 4. Verificar Enriquecimiento IA (flag ON y orquestador cableado)
    assert "llm_explanation" in advisory
    assert "context_used" in advisory
    assert isinstance(advisory["context_used"], list)

    # 5. Verificar auditoría persistida en la DB temporal
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM decision_events WHERE tenant_id = 'tenant_1'")
    count = cursor.fetchone()[0]
    conn.close()

    assert count == 1


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
