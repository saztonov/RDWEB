"""Тесты для admin endpoints."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient


def test_admin_health_forbidden_for_user(client: TestClient):
    """GET /api/admin/health → 403 для обычного пользователя."""
    response = client.get("/api/admin/health")
    assert response.status_code == 403


def test_admin_events_forbidden_for_user(client: TestClient):
    """GET /api/admin/events → 403 для обычного пользователя."""
    response = client.get("/api/admin/events")
    assert response.status_code == 403


def test_admin_health_ok_for_admin(admin_client: TestClient, mock_supabase: MagicMock):
    """GET /api/admin/health → 200 для admin."""
    # Мокаем service_health_checks
    mock_supabase.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = (
        MagicMock(data=[])
    )

    import app.routes.admin as admin_mod

    original = admin_mod.get_supabase
    admin_mod.get_supabase = lambda: mock_supabase

    try:
        response = admin_client.get("/api/admin/health")
        assert response.status_code == 200
        data = response.json()
        assert "services" in data
        assert "overall" in data
        assert data["overall"] == "unknown"
    finally:
        admin_mod.get_supabase = original


def test_admin_events_ok_for_admin(admin_client: TestClient, mock_supabase: MagicMock):
    """GET /api/admin/events → 200 для admin с пагинацией."""
    count_mock = MagicMock(count=0)
    data_mock = MagicMock(data=[])

    table_mock = MagicMock()
    mock_supabase.table.return_value = table_mock

    # count query
    table_mock.select.return_value.execute.return_value = count_mock
    # data query
    table_mock.select.return_value.order.return_value.range.return_value.execute.return_value = data_mock

    import app.routes.admin as admin_mod

    original = admin_mod.get_supabase
    admin_mod.get_supabase = lambda: mock_supabase

    try:
        response = admin_client.get("/api/admin/events")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "meta" in data
        assert data["meta"]["total"] == 0
    finally:
        admin_mod.get_supabase = original
