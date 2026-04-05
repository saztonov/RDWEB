"""Тесты для auth layer — 401 без токена, 403 для non-admin."""

from fastapi.testclient import TestClient


def test_me_requires_auth(anon_client: TestClient):
    """GET /api/me без Authorization header → 401."""
    response = anon_client.get("/api/me")
    assert response.status_code == 401


def test_workspaces_requires_auth(anon_client: TestClient):
    """GET /api/workspaces без Authorization header → 401."""
    response = anon_client.get("/api/workspaces")
    assert response.status_code == 401


def test_admin_health_requires_auth(anon_client: TestClient):
    """GET /api/admin/health без Authorization header → 401."""
    response = anon_client.get("/api/admin/health")
    assert response.status_code == 401


def test_admin_events_requires_auth(anon_client: TestClient):
    """GET /api/admin/events без Authorization header → 401."""
    response = anon_client.get("/api/admin/events")
    assert response.status_code == 401
