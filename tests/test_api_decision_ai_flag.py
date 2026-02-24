from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)

VALID_HEADERS = {"X-API-Key": "key-client-1"}


def test_decision_api_ai_flag_off(monkeypatch):
    monkeypatch.setattr("app.api.main.ENABLE_AI_ADVISORY", False)

    payload = {
        "hosting_type": "vps",
        "project_type": "ecommerce",
        "symptoms": ["checkout_error"],
        "recent_changes": ["deploy"],
        "estimated_impact": "high",
    }

    response = client.post("/decision", json=payload, headers=VALID_HEADERS)
    data = response.json()

    assert response.status_code == 200
    assert "advisory" in data
    assert data["advisory"].get("llm_explanation") is None


def test_decision_api_ai_flag_on(monkeypatch):
    monkeypatch.setattr("app.api.main.ENABLE_AI_ADVISORY", True)

    payload = {
        "hosting_type": "vps",
        "project_type": "ecommerce",
        "symptoms": ["checkout_error"],
        "recent_changes": ["deploy"],
        "estimated_impact": "high",
    }

    response = client.post("/decision", json=payload, headers=VALID_HEADERS)
    data = response.json()

    assert response.status_code == 200
    assert "advisory" in data
