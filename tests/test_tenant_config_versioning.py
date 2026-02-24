import pytest
from app.infra.config.repository import TenantConfigRepository


def test_new_config_version_deactivates_previous(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.infra.config.sqlite.DB_PATH",
        tmp_path / "cfg.sqlite",
    )

    repo = TenantConfigRepository()

    # Versión 1
    v1 = repo.create_new_version(
        tenant_id="t1",
        kind="prompt",
        content={"tone": "formal"},
    )
    assert v1.version == 1
    assert v1.active is True

    # Versión 2
    v2 = repo.create_new_version(
        tenant_id="t1",
        kind="prompt",
        content={"tone": "muy_conservador"},
    )
    assert v2.version == 2
    assert v2.active is True

    # Verificar que solo v2 está activa
    active = repo.get_active("t1", "prompt")
    assert active["tone"] == "muy_conservador"

    # Verificar historial
    history = repo.get_all_versions("t1", "prompt")
    assert len(history) == 2
    assert history[0].version == 2
    assert history[0].active is True
    assert history[1].version == 1
    assert history[1].active is False


def test_get_active_empty_for_non_existent_tenant():
    repo = TenantConfigRepository()
    active = repo.get_active("non_existent", "rules")
    assert active == {}
