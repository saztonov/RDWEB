"""Тесты для workspace endpoints."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from .conftest import TEST_WORKSPACE_ID


def test_list_workspaces_returns_list(client: TestClient, mock_supabase: MagicMock):
    """GET /api/workspaces возвращает список workspace-ов."""
    # Мокаем workspace_members + workspaces join
    mock_result = MagicMock(
        data=[
            {
                "role": "member",
                "workspaces": {
                    "id": TEST_WORKSPACE_ID,
                    "name": "Demo",
                    "slug": "demo",
                    "settings_json": {},
                    "created_at": "2026-04-01T00:00:00+00:00",
                },
            }
        ]
    )
    mock_count = MagicMock(count=1)

    # Настройка цепочки вызовов
    table_mock = MagicMock()
    mock_supabase.table.return_value = table_mock
    table_mock.select.return_value.eq.return_value.execute.return_value = mock_result
    table_mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_count

    import app.routes.workspaces as ws_mod

    original = ws_mod.get_supabase
    ws_mod.get_supabase = lambda: mock_supabase

    try:
        response = client.get("/api/workspaces")
        assert response.status_code == 200
        data = response.json()
        assert "workspaces" in data
        assert isinstance(data["workspaces"], list)
    finally:
        ws_mod.get_supabase = original


def test_admin_forbidden_for_regular_user(client: TestClient):
    """GET /api/admin/health возвращает 403 для обычного пользователя."""
    response = client.get("/api/admin/health")
    assert response.status_code == 403
