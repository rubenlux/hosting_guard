from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_request_with_valid_tenant_key():
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


def test_request_with_invalid_tenant_key():
    headers = {"X-API-Key": "invalid-key"}

    response = client.post("/decision", json={}, headers=headers)

    assert response.status_code == 401
