"""Pydantic schemas для OCR sources API.

Ключевое: credentials_json НЕ включается в ответы — секреты не уходят на фронт.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class OcrSourceResponse(BaseModel):
    """OCR source без credentials — для фронта."""

    id: str
    source_type: str
    name: str
    base_url: str
    deployment_mode: str
    is_enabled: bool
    concurrency_limit: int
    timeout_sec: int
    health_status: str
    last_health_at: datetime | None = None
    capabilities_json: dict = {}
    created_at: datetime
    updated_at: datetime


class OcrSourceListResponse(BaseModel):
    """Список OCR source-ов."""

    sources: list[OcrSourceResponse]


class OcrSourceModelResponse(BaseModel):
    """Модель из кэша ocr_source_models_cache."""

    model_id: str
    model_name: str
    context_length: int | None = None
    supports_vision: bool = False
    fetched_at: datetime


class OcrSourceModelsListResponse(BaseModel):
    """Список моделей для source-а."""

    source_id: str
    models: list[OcrSourceModelResponse]


class HealthCheckResponse(BaseModel):
    """Результат healthcheck-а source-а."""

    source_id: str
    source_name: str
    health_status: str
    response_time_ms: int | None = None
    details: dict = {}
    checked_at: datetime
