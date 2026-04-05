"""Тесты для GET /api/me."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.auth.supabase_client import get_supabase
from app.main import app

from .conftest import TEST_USER_ID, TEST_WORKSPACE_ID


def test_me_returns_user_info(client: TestClient, mock_supabase: MagicMock):
    """GET /api/me возвращает данные текущего пользователя."""
    # Мокаем workspace_members query
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[
            {
                "workspace_id": TEST_WORKSPACE_ID,
                "role": "member",
                "workspaces": {"name": "Demo Workspace"},
            }
        ]
    )
    # Мокаем system_events insert (audit)
    mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])

    # Подменяем get_supabase на уровне модуля
    import app.routes.me as me_mod
    import app.permissions.audit as audit_mod

    original_me = me_mod.get_supabase
    original_audit = audit_mod.get_supabase
    me_mod.get_supabase = lambda: mock_supabase
    audit_mod.get_supabase = lambda: mock_supabase

    try:
        response = client.get("/api/me")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == TEST_USER_ID
        assert data["email"] == "user@test.com"
        assert data["is_admin"] is False
        assert isinstance(data["workspaces"], list)
    finally:
        me_mod.get_supabase = original_me
        audit_mod.get_supabase = original_audit
