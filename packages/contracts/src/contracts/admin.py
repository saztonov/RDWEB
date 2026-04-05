"""Schemas для admin endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .common import PaginatedMeta


class SystemEventResponse(BaseModel):
    """Системное событие."""

    id: str
    event_type: str
    severity: str
    source_service: str | None = None
    payload_json: dict = {}
    created_at: datetime


class SystemEventListResponse(BaseModel):
    """Пагинированный список системных событий."""

    events: list[SystemEventResponse]
    meta: PaginatedMeta


class ServiceHealthResponse(BaseModel):
    """Статус здоровья сервиса."""

    service_name: str
    status: str
    response_time_ms: int | None = None
    checked_at: datetime


class AdminHealthResponse(BaseModel):
    """Общий health-статус всех сервисов."""

    services: list[ServiceHealthResponse]
    overall: str
