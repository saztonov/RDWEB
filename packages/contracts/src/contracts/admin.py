"""Schemas для admin endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .common import PaginatedMeta


# ──────────────────────────────────────────────────────────────────────
# System Events
# ──────────────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────────────
# Service Health
# ──────────────────────────────────────────────────────────────────────

class ServiceHealthResponse(BaseModel):
    """Статус здоровья сервиса."""

    service_name: str
    status: str
    response_time_ms: int | None = None
    details_json: dict | None = None
    checked_at: datetime


# ──────────────────────────────────────────────────────────────────────
# Queue & Workers
# ──────────────────────────────────────────────────────────────────────

class QueueSummaryResponse(BaseModel):
    """Сводка очереди задач."""

    size: int
    max_capacity: int
    can_accept: bool


class WorkerHeartbeatResponse(BaseModel):
    """Heartbeat одного worker-а."""

    worker_name: str
    queue_name: str | None = None
    host: str | None = None
    pid: int | None = None
    memory_mb: float | None = None
    active_tasks: int = 0
    last_seen_at: datetime


class WorkerSummaryResponse(BaseModel):
    """Сводка по worker-ам."""

    active_count: int
    workers: list[WorkerHeartbeatResponse]


# ──────────────────────────────────────────────────────────────────────
# Admin Overview
# ──────────────────────────────────────────────────────────────────────

class AdminHealthResponse(BaseModel):
    """Общий health-статус: сервисы + очередь + воркеры."""

    services: list[ServiceHealthResponse]
    overall: str
    queue: QueueSummaryResponse | None = None
    workers: WorkerSummaryResponse | None = None


# ──────────────────────────────────────────────────────────────────────
# Admin OCR Sources
# ──────────────────────────────────────────────────────────────────────

class AdminOcrSourceResponse(BaseModel):
    """Расширенная информация об OCR source для admin panel."""

    id: str
    source_type: str
    name: str
    base_url: str | None = None
    deployment_mode: str | None = None
    is_enabled: bool = True
    concurrency_limit: int = 4
    timeout_sec: int = 120
    health_status: str = "unknown"
    last_health_at: datetime | None = None
    capabilities_json: dict = {}
    # Расширенные поля admin
    last_error: str | None = None
    last_response_time_ms: int | None = None
    cached_models_count: int = 0


class AdminOcrSourceDetailResponse(AdminOcrSourceResponse):
    """Детальная информация с историей health checks и моделями."""

    recent_health_checks: list[ServiceHealthResponse] = []
    cached_models: list[dict] = []


class AdminOcrSourceListResponse(BaseModel):
    """Список OCR sources для admin panel."""

    sources: list[AdminOcrSourceResponse]


# ──────────────────────────────────────────────────────────────────────
# Admin Recognition Runs
# ──────────────────────────────────────────────────────────────────────

class AdminRunResponse(BaseModel):
    """Recognition run для admin panel."""

    id: str
    document_id: str
    document_title: str | None = None
    initiated_by: str | None = None
    run_mode: str
    status: str
    total_blocks: int = 0
    dirty_blocks: int = 0
    processed_blocks: int = 0
    recognized_blocks: int = 0
    failed_blocks: int = 0
    manual_review_blocks: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class AdminRunListResponse(BaseModel):
    """Пагинированный список recognition runs."""

    runs: list[AdminRunResponse]
    meta: PaginatedMeta


class AdminRunBlockResponse(BaseModel):
    """Блок в контексте recognition run."""

    block_id: str
    page_number: int
    block_kind: str
    current_status: str
    attempt_count: int = 0
    last_error: str | None = None


class AdminRunDetailResponse(AdminRunResponse):
    """Детали run-а с блоками."""

    blocks: list[AdminRunBlockResponse] = []


# ──────────────────────────────────────────────────────────────────────
# Block Incidents
# ──────────────────────────────────────────────────────────────────────

class BlockIncidentResponse(BaseModel):
    """Инцидент: failed recognition attempt с контекстом."""

    attempt_id: str
    run_id: str | None = None
    block_id: str
    document_id: str
    document_title: str | None = None
    page_number: int
    block_kind: str
    source_id: str | None = None
    source_name: str | None = None
    model_name: str | None = None
    prompt_template_id: str | None = None
    attempt_no: int = 1
    fallback_no: int = 0
    error_code: str | None = None
    error_message: str | None = None
    status: str
    created_at: datetime


class BlockIncidentListResponse(BaseModel):
    """Пагинированный список инцидентов."""

    incidents: list[BlockIncidentResponse]
    meta: PaginatedMeta
