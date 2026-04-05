"""Типы данных для OCR-провайдеров.

Frozen dataclass-ы, не зависящие от БД и фреймворков.
Используются в ocr_core, API и worker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


# ─── Enum-ы ──────────────────────────────────────────────────────────────────


class SourceType(StrEnum):
    """Тип OCR-провайдера."""

    OPENROUTER = "openrouter"
    LMSTUDIO = "lmstudio"


class DeploymentMode(StrEnum):
    """Режим деплоя source-а."""

    MANAGED_API = "managed_api"
    DOCKER = "docker"
    REMOTE_NGROK = "remote_ngrok"
    PRIVATE_URL = "private_url"


class HealthStatus(StrEnum):
    """Статус доступности source-а."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


# ─── Конфигурация source-а ───────────────────────────────────────────────────


@dataclass(frozen=True)
class SourceConfig:
    """Конфигурация source-а — создаётся из строки БД ocr_sources."""

    id: str
    source_type: SourceType
    name: str
    base_url: str
    deployment_mode: DeploymentMode
    credentials: dict[str, Any]
    concurrency_limit: int
    timeout_sec: int
    capabilities: dict[str, Any] = field(default_factory=dict)


# ─── Результаты операций ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class HealthResult:
    """Результат healthcheck-а провайдера."""

    status: HealthStatus
    response_time_ms: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelInfo:
    """Информация о модели, доступной у провайдера."""

    model_id: str
    model_name: str
    context_length: int | None = None
    supports_vision: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecognizeResult:
    """Результат распознавания блока."""

    text: str
    is_error: bool = False
    error_code: str | None = None
    error_message: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
