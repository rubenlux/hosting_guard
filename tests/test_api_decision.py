# tests/test_api_decision.py

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)

VALID_HEADERS = {"X-API-Key": "key-client-1"}


def test_decision_endpoint_wordpress_error_500():
    payload = {
        "hosting_type": "shared",
        "project_type": "wordpress",
        "symptoms": ["error_500"],
        "recent_changes": ["plugin_update"],
        "estimated_impact": "medium",
    }

    response = client.post("/decision", json=payload, headers=VALID_HEADERS)

    assert response.status_code == 200

    data = response.json()

    # Contrato básico
    assert "decision_id" in data
    assert "diagnosis" in data
    assert "actions_evaluation" in data
    assert "overall_status" in data
    assert "tenant_id" in data

    # Coherencia mínima
    assert data["overall_status"] in {
        "requires_human",
        "blocked",
        "ready_for_execution",
        "unknown",
    }


def test_decision_endpoint_ecommerce_checkout_error():
    payload = {
        "hosting_type": "vps",
        "project_type": "ecommerce",
        "symptoms": ["checkout_error"],
        "recent_changes": ["deploy"],
        "estimated_impact": "high",
    }

    response = client.post("/decision", json=payload, headers=VALID_HEADERS)

    assert response.status_code == 200

    data = response.json()

    # En ecommerce crítico nunca debe ser ready_for_execution
    assert data["overall_status"] in {"requires_human", "blocked"}

    # Todas las acciones deben requerir humano
    for action in data["actions_evaluation"]:
        assert action["requires_human_approval"] is True

    # La IA debe haber dado su opinión
    assert "advisory" in data
    assert "summary" in data["advisory"]
    assert data["advisory"]["requires_human_attention"] is True


def test_decision_endpoint_includes_advisory():
    payload = {
        "hosting_type": "vps",
        "project_type": "ecommerce",
        "symptoms": ["checkout_error"],
        "recent_changes": ["deploy"],
        "estimated_impact": "high",
    }

    response = client.post("/decision", json=payload, headers=VALID_HEADERS)

    assert response.status_code == 200

    data = response.json()

    assert "advisory" in data
    assert data["advisory"]["requires_human_attention"] is True
    assert "summary" in data["advisory"]


def test_decision_endpoint_invalid_payload():
    payload = {
        # falta hosting_type
        "project_type": "wordpress",
        "symptoms": "error_500",  # debería ser lista
        "estimated_impact": "medium",
    }

    # Aquí el error de validación 422 ocurre antes de la autenticación en FastAPI usualmente
    # si el payload está mal formed, pero Depends se ejecuta antes del body validation
    # si está en la firma de la función. En nuestro caso, depends(resolve_tenant)
    # requiere el header. Si no lo mandamos, fallará con 422 (header required).

    response = client.post("/decision", json=payload, headers=VALID_HEADERS)

    assert response.status_code == 422
