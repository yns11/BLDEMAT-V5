from __future__ import annotations

import pytest
from bl_core import rbac
from bl_core.config import reset_settings_cache


@pytest.fixture(autouse=True)
def strict_mode(monkeypatch):
    monkeypatch.setenv("BL_RBAC_MODE", "strict")
    monkeypatch.setenv("BL_ENVIRONMENT", "local")
    monkeypatch.delenv("BL_BOOTSTRAP_ADMINS", raising=False)
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_unknown_user_has_no_access(monkeypatch):
    monkeypatch.setattr(rbac.repository, "roles_utilisateur", lambda _: [])
    context = rbac.contexte_rbac("unknown@example.com")
    assert context["roles"] == []
    assert rbac.operations_autorisees(context) == []
    assert rbac.niveau_vue("Tableau de bord", context) == rbac.AUCUN


def test_repository_failure_closes_access(monkeypatch):
    def failure(_):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(rbac.repository, "roles_utilisateur", failure)
    context = rbac.contexte_rbac("user@example.com")
    assert context["indisponible"] is True
    assert context["roles"] == []


def test_bootstrap_admin_is_explicit(monkeypatch):
    monkeypatch.setenv("BL_BOOTSTRAP_ADMINS", "bootstrap@example.com")
    reset_settings_cache()
    context = rbac.contexte_rbac("BOOTSTRAP@example.com")
    assert context["roles"] == [rbac.ROLE_ADMIN]


def test_server_side_guard_rejects_write(monkeypatch):
    context = {"actif": True, "roles": [rbac.ROLE_FINANCE]}
    with pytest.raises(PermissionError):
        rbac.exiger_vue("BL réception", context, rbac.MODIFICATION)
