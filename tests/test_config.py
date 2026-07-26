from __future__ import annotations

import pytest
from bl_core.config import get_settings, reset_settings_cache


@pytest.fixture(autouse=True)
def clear_settings(monkeypatch):
    for name in (
        "BL_ENVIRONMENT",
        "BL_PG_SCHEMA",
        "BL_RBAC_MODE",
        "BL_IMAGE_BACKEND",
        "BL_VOLUME_PATH",
        "BL_BOOTSTRAP_ADMINS",
    ):
        monkeypatch.delenv(name, raising=False)
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_local_defaults_are_safe():
    settings = get_settings()
    assert settings.environment == "local"
    assert settings.rbac_mode == "strict"
    assert settings.optimistic_locking is True


def test_rbac_cannot_be_disabled_in_production(monkeypatch):
    monkeypatch.setenv("BL_ENVIRONMENT", "prod")
    monkeypatch.setenv("BL_RBAC_MODE", "disabled")
    monkeypatch.setenv("BL_VOLUME_PATH", "/Volumes/catalog/schema/documents")
    reset_settings_cache()
    with pytest.raises(RuntimeError, match="RBAC"):
        get_settings()


def test_production_volume_path_is_validated(monkeypatch):
    monkeypatch.setenv("BL_ENVIRONMENT", "prod")
    monkeypatch.setenv("BL_VOLUME_PATH", "/tmp/documents")
    reset_settings_cache()
    with pytest.raises(RuntimeError, match="BL_VOLUME_PATH"):
        get_settings()


def test_bootstrap_admins_are_normalized(monkeypatch):
    monkeypatch.setenv("BL_BOOTSTRAP_ADMINS", " Admin@Example.COM, ops@example.com ")
    reset_settings_cache()
    assert get_settings().bootstrap_admins == ("admin@example.com", "ops@example.com")
