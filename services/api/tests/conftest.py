"""Shared fixtures для тестов backend API."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.models import CurrentUser
from app.auth.supabase_client import get_supabase
from app.main import app

# Фиксированные UUID для воспроизводимости
TEST_USER_ID = "00000000-0000-0000-0000-000000000099"
TEST_ADMIN_ID = "00000000-0000-0000-0000-000000000001"
TEST_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
TEST_DOCUMENT_ID = "00000000-0000-0000-0000-000000000050"


@pytest.fixture()
def mock_user() -> CurrentUser:
    return CurrentUser(id=TEST_USER_ID, email="user@test.com", is_admin=False)


@pytest.fixture()
def mock_admin() -> CurrentUser:
    return CurrentUser(id=TEST_ADMIN_ID, email="admin@test.com", is_admin=True)


@pytest.fixture()
def mock_supabase() -> MagicMock:
    """Мок Supabase client для тестов без реального подключения."""
    return MagicMock()


@pytest.fixture()
def client(mock_user: CurrentUser, mock_supabase: MagicMock) -> TestClient:
    """TestClient с override: обычный пользователь."""
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_client(mock_admin: CurrentUser, mock_supabase: MagicMock) -> TestClient:
    """TestClient с override: admin пользователь."""
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    app.dependency_overrides[get_supabase] = lambda: mock_supabase
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def anon_client() -> TestClient:
    """TestClient без auth override — для тестов 401."""
    app.dependency_overrides.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()
