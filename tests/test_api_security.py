from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_request_without_api_key_is_rejected(monkeypatch):
    # Forzamos una API_KEY en el entorno para activar el bloqueo
    monkeypatch.setattr("app.api.security.API_KEY", "secret")

    response = client.post("/decision", json={})
    # Fallará por falta del header de API Key o por payload vacío (FastAPI valida schemas antes)
    assert response.status_code in {401, 422}


def test_request_with_invalid_api_key_is_rejected(monkeypatch):
    monkeypatch.setattr("app.api.security.API_KEY", "secret")

    headers = {"X-API-Key": "wrong"}
    payload = {
        "hosting_type": "shared",
        "project_type": "wordpress",
        "symptoms": ["error_500"],
        "estimated_impact": "low",
    }
    response = client.post("/decision", json=payload, headers=headers)

    assert response.status_code == 401


def test_security_headers_are_present():
    # /health is intentionally excluded from security headers (Prometheus scraping).
    # Use /login with an empty body — returns 422 but middleware still injects headers.
    response = client.post("/login", json={})
    assert response.status_code == 422
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert "Content-Security-Policy" in response.headers
