import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.infra.audit import sqlite as audit_sqlite


@pytest.fixture
def client(tmp_path, monkeypatch):
    # DB de auditoría temporal para aislamiento total en tests
    db_file = tmp_path / "audit.sqlite"
    monkeypatch.setattr(audit_sqlite, "DB_PATH", db_file)

    # Reiniciar la DB para cada test
    audit_sqlite.init_db()

    # Feature flags activado por defecto para E2E
    # Nota: monkeypatching app.api.main.ENABLE_AI_ADVISORY directamente
    # ya que se lee al importar el módulo.
    monkeypatch.setattr("app.api.main.ENABLE_AI_ADVISORY", True)

    return TestClient(app)
