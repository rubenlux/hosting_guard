"""
Tests para TenantConfigRepository — sin PostgreSQL real.
Se usa un cursor mock con estado en memoria para simular versioning.
"""
import json
from unittest.mock import MagicMock, patch, call


class _InMemoryConfigStore:
    """Simula las tablas tenant_configs en memoria para los tests."""

    def __init__(self):
        self._rows: list[dict] = []
        self._last_result = None

    def execute(self, sql: str, params=None):
        sql_up = sql.strip().upper()

        if sql_up.startswith("UPDATE"):
            # Desactiva versiones anteriores
            for row in self._rows:
                if (params and row["tenant_id"] == params[0]
                        and row["kind"] == params[1] and row["active"]):
                    row["active"] = 0

        elif "SELECT MAX(VERSION)" in sql_up:
            tenant_id, kind = params[0], params[1]
            versions = [r["version"] for r in self._rows
                        if r["tenant_id"] == tenant_id and r["kind"] == kind]
            max_v = max(versions) if versions else None
            self._last_result = {"max_version": max_v}

        elif sql_up.startswith("INSERT"):
            config_id, tenant_id, version, kind, content, created_at = (
                params[0], params[1], params[2], params[3], params[4], params[5]
            )
            self._rows.append({
                "config_id": config_id,
                "tenant_id": tenant_id,
                "version": version,
                "kind": kind,
                "content": content,
                "created_at": created_at,
                "active": 1,
            })
            self._last_result = None

        elif "SELECT CONTENT" in sql_up:
            tenant_id, kind = params[0], params[1]
            active = [r for r in self._rows
                      if r["tenant_id"] == tenant_id and r["kind"] == kind and r["active"]]
            self._last_result = active[-1] if active else None

        elif sql_up.startswith("SELECT *"):
            tenant_id, kind = params[0], params[1]
            results = [r for r in self._rows
                       if r["tenant_id"] == tenant_id and r["kind"] == kind]
            results.sort(key=lambda r: r["version"], reverse=True)
            self._last_result = results

        return self

    def fetchone(self):
        r = self._last_result
        self._last_result = None
        return r

    def fetchall(self):
        r = self._last_result if isinstance(self._last_result, list) else []
        self._last_result = None
        return r

    @property
    def rowcount(self): return 1


def _make_mock_conn(store):
    conn = MagicMock()
    conn.cursor.return_value = store
    conn.commit.return_value = None
    return conn


def test_new_config_version_deactivates_previous():
    from app.infra.config.repository import TenantConfigRepository

    store = _InMemoryConfigStore()
    conn = _make_mock_conn(store)

    with patch("app.infra.config.repository.get_connection", return_value=conn), \
         patch("app.infra.config.repository.init_db"):
        repo = TenantConfigRepository()

        v1 = repo.create_new_version("t1", "prompt", {"tone": "formal"})
        assert v1.version == 1
        assert v1.active is True

        v2 = repo.create_new_version("t1", "prompt", {"tone": "muy_conservador"})
        assert v2.version == 2
        assert v2.active is True

        # Solo v2 debe estar activa en el store
        active_rows = [r for r in store._rows
                       if r["tenant_id"] == "t1" and r["kind"] == "prompt" and r["active"]]
        assert len(active_rows) == 1
        assert json.loads(active_rows[0]["content"])["tone"] == "muy_conservador"


def test_get_active_returns_latest():
    from app.infra.config.repository import TenantConfigRepository

    store = _InMemoryConfigStore()
    conn = _make_mock_conn(store)

    with patch("app.infra.config.repository.get_connection", return_value=conn), \
         patch("app.infra.config.repository.init_db"):
        repo = TenantConfigRepository()
        repo.create_new_version("t1", "prompt", {"tone": "formal"})
        repo.create_new_version("t1", "prompt", {"tone": "muy_conservador"})
        active = repo.get_active("t1", "prompt")

    assert active["tone"] == "muy_conservador"


def test_get_active_empty_for_non_existent_tenant():
    from app.infra.config.repository import TenantConfigRepository

    store = _InMemoryConfigStore()
    conn = _make_mock_conn(store)

    with patch("app.infra.config.repository.get_connection", return_value=conn), \
         patch("app.infra.config.repository.init_db"):
        repo = TenantConfigRepository()
        result = repo.get_active("non_existent", "rules")

    assert result == {}


def test_version_increments_per_tenant_and_kind():
    from app.infra.config.repository import TenantConfigRepository

    store = _InMemoryConfigStore()
    conn = _make_mock_conn(store)

    with patch("app.infra.config.repository.get_connection", return_value=conn), \
         patch("app.infra.config.repository.init_db"):
        repo = TenantConfigRepository()
        repo.create_new_version("t1", "prompt", {"v": 1})
        repo.create_new_version("t1", "prompt", {"v": 2})
        v3 = repo.create_new_version("t1", "prompt", {"v": 3})
        v_rules = repo.create_new_version("t1", "rules", {"r": 1})

    assert v3.version == 3
    assert v_rules.version == 1  # diferente kind → empieza en 1
