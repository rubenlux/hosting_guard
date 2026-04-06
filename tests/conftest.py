import os
import pytest
from fastapi.testclient import TestClient

# Deshabilitar rate limiting en todos los tests.
# Debe hacerse ANTES de importar la app para que slowapi lo respete.
os.environ.setdefault("TESTING", "1")

from app.api.main import app
from app.infra.audit import sqlite as audit_sqlite


@pytest.fixture(autouse=True, scope="session")
def disable_rate_limiter():
    """Deshabilita el rate limiter de slowapi en todo el test suite."""
    from app.api.rate_limit import limiter
    limiter.enabled = False
    yield
    limiter.enabled = True


@pytest.fixture
def client(tmp_path, monkeypatch):
    # DB de auditoría temporal para aislamiento total en tests
    db_file = tmp_path / "audit.sqlite"
    monkeypatch.setattr(audit_sqlite, "DB_PATH", db_file)

    # Reiniciar conexión thread-local para evitar contaminación entre tests
    if hasattr(audit_sqlite._local, "conn") and audit_sqlite._local.conn is not None:
        try:
            audit_sqlite._local.conn._conn.close()
        except Exception:
            pass
        audit_sqlite._local.conn = None

    # Reiniciar la DB para cada test
    audit_sqlite.init_db()

    monkeypatch.setattr("app.api.main.ENABLE_AI_ADVISORY", True)

    return TestClient(app)
