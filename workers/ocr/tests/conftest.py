"""Shared fixtures для OCR pipeline тестов."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from ocr_core.provider_types import RecognizeResult


# ── Фабрики те��товых данных ──────────────────────────────────────────


def make_block_data(
    block_id: str | None = None,
    block_kind: str = "text",
    page_number: int = 1,
    status: str = "queued",
    **overrides,
) -> dict:
    """Создать тестовые данные блока (как из БД)."""
    bid = block_id or str(uuid.uuid4())
    data = {
        "id": bid,
        "document_id": str(uuid.uuid4()),
        "page_number": page_number,
        "block_kind": block_kind,
        "shape_type": "rect",
        "bbox_json": {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.05},
        "polygon_json": None,
        "reading_order": 1,
        "geometry_rev": 1,
        "content_rev": 1,
        "manual_lock": False,
        "route_source_id": None,
        "route_model_name": None,
        "prompt_template_id": None,
        "current_text": None,
        "current_structured_json": None,
        "current_render_html": None,
        "current_status": status,
        "current_attempt_id": None,
        "current_crop_key": None,
        "crop_upload_state": "none",
        "crop_sha256": None,
        "last_recognition_signature": None,
        "created_by": None,
        "updated_by": None,
        "deleted_at": None,
    }
    data.update(overrides)
    return data


def make_route_data(
    source_id: str | None = None,
    model_name: str = "qwen/qwen3-vl",
    prompt_template_id: str | None = None,
    fallback_chain: list | None = None,
) -> dict:
    """Создать тестовую profile_route запись."""
    return {
        "primary_source_id": source_id or str(uuid.uuid4()),
        "primary_model_name": model_name,
        "default_prompt_template_id": prompt_template_id or str(uuid.uuid4()),
        "fallback_chain_json": fallback_chain,
    }


def make_template_data(
    template_id: str | None = None,
    parser_strategy: str = "plain_text",
) -> dict:
    """Создать тестовый prompt template."""
    return {
        "id": template_id or str(uuid.uuid4()),
        "template_key": "test_template",
        "version": 1,
        "is_active": True,
        "block_kind": "text",
        "source_type": "openrouter",
        "system_template": "You are an OCR system.",
        "user_template": "Recognize the image content for block {BLOCK_ID}.",
        "parser_strategy": parser_strategy,
        "output_schema_json": None,
    }


def make_source_data(source_id: str | None = None) -> dict:
    """Создать тестовый ocr_source."""
    return {
        "id": source_id or str(uuid.uuid4()),
        "source_type": "openrouter",
        "name": "test-openrouter",
        "base_url": "https://openrouter.ai",
        "deployment_mode": "managed_api",
        "credentials_json": {"api_key": "test-key"},
        "concurrency_limit": 4,
        "timeout_sec": 120,
        "capabilities_json": {},
        "is_enabled": True,
    }


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def fake_page_image() -> Image.Image:
    """Fake page image 1000x1400 (примерно A4 пропорции)."""
    return Image.new("RGB", (1000, 1400), color=(255, 255, 255))


@pytest.fixture
def tmp_workspace(tmp_path) -> Path:
    """Временная директория для workspace."""
    ws = tmp_path / "workspaces"
    ws.mkdir()
    return ws


class MockSupabaseTable:
    """Mock дл�� одной таблицы Supabase."""

    def __init__(self, data: list[dict] | None = None):
        self._data = data or []
        self._calls: list[dict] = []

    def select(self, *args, **kwargs):
        self._calls.append({"op": "select", "args": args})
        return self

    def insert(self, data, **kwargs):
        self._calls.append({"op": "insert", "data": data})
        if isinstance(data, dict):
            if "id" not in data:
                data["id"] = str(uuid.uuid4())
            self._data.append(data)
        return self

    def update(self, data, **kwargs):
        self._calls.append({"op": "update", "data": data})
        return self

    def delete(self, **kwargs):
        self._calls.append({"op": "delete"})
        return self

    def eq(self, field, value):
        return self

    def in_(self, field, values):
        return self

    def is_(self, field, value):
        return self

    def order(self, field, **kwargs):
        return self

    def limit(self, n):
        return self

    def single(self):
        return self

    def maybe_single(self):
        return self

    def execute(self):
        result = MagicMock()
        result.data = self._data[-1] if self._data else None
        if len(self._data) > 1:
            result.data = self._data
        return result


class MockSupabase:
    """Mock Supabase client с настраиваемыми ответами таблиц."""

    def __init__(self):
        self._tables: dict[str, MockSupabaseTable] = {}

    def set_table_data(self, table_name: str, data: list[dict]) -> None:
        self._tables[table_name] = MockSupabaseTable(data)

    def table(self, name: str):
        if name not in self._tables:
            self._tables[name] = MockSupabaseTable()
        return self._tables[name]
