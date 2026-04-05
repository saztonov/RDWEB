"""Тесты для health endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    """GET /health возвращает ok=true."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_readiness_returns_json(client):
    """GET /health/ready возвращает JSON с checks."""
    response = client.get("/health/ready")
    data = response.json()
    assert "ready" in data
    assert "checks" in data
    assert set(data["checks"].keys()) == {"redis", "supabase", "config"}
