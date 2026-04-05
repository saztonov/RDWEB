"""Тесты для document endpoints."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from .conftest import TEST_DOCUMENT_ID, TEST_USER_ID, TEST_WORKSPACE_ID


def test_list_documents_requires_workspace_id(client: TestClient):
    """GET /api/documents без workspace_id → 422."""
    response = client.get("/api/documents")
    assert response.status_code in (400, 422)


def test_list_documents_checks_membership(client: TestClient, mock_supabase: MagicMock):
    """GET /api/documents с workspace_id проверяет membership."""
    # Мокаем workspace_members — пользователь не member
    table_mock = MagicMock()
    mock_supabase.table.return_value = table_mock

    # maybe_single возвращает None (не member)
    table_mock.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
        MagicMock(data=None)
    )

    import app.permissions.checks as checks_mod

    original = checks_mod.get_supabase
    checks_mod.get_supabase = lambda: mock_supabase

    try:
        response = client.get(f"/api/documents?workspace_id={TEST_WORKSPACE_ID}")
        assert response.status_code == 404  # 404, не 403
    finally:
        checks_mod.get_supabase = original
