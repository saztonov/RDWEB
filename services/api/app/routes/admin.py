"""Admin endpoints — overview health, events. Доступны только global admin.

Healthcheck OCR sources перенесён в admin_sources.py.
"""

from __future__ import annotations

import redis as redis_lib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from contracts import (
    AdminHealthResponse,
    PaginatedMeta,
    QueueSummaryResponse,
    ServiceHealthResponse,
    SystemEventListResponse,
    SystemEventResponse,
    WorkerHeartbeatResponse,
    WorkerSummaryResponse,
)

from ..auth import CurrentUser, get_supabase
from ..auth.dependencies import require_admin
from ..config import get_settings

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/health", response_model=AdminHealthResponse)
def admin_health(user: CurrentUser = Depends(require_admin)) -> AdminHealthResponse:
    """Health-статус всех сервисов + очередь + воркеры. Только для admin."""
    sb = get_supabase()
    settings = get_settings()

    # ── Service health checks (дедупликация по service_name) ──
    result = (
        sb.table("service_health_checks")
        .select("*")
        .order("checked_at", desc=True)
        .limit(100)
        .execute()
    )

    seen: dict[str, dict] = {}
    for row in result.data or []:
        name = row["service_name"]
        if name not in seen:
            seen[name] = row

    services = [
        ServiceHealthResponse(
            service_name=row["service_name"],
            status=row["status"],
            response_time_ms=row.get("response_time_ms"),
            details_json=row.get("details_json"),
            checked_at=row["checked_at"],
        )
        for row in seen.values()
    ]

    # ── Overall status ──
    statuses = {s.status for s in services}
    if not services:
        overall = "unknown"
    elif "unavailable" in statuses:
        overall = "unavailable"
    elif "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "healthy"

    # ── Queue summary ──
    queue: QueueSummaryResponse | None = None
    try:
        r = redis_lib.from_url(settings.redis_url, socket_connect_timeout=3, decode_responses=True)
        size = r.llen("celery") or 0
        r.close()
        queue = QueueSummaryResponse(size=size, max_capacity=100, can_accept=size < 100)
    except Exception:
        queue = QueueSummaryResponse(size=-1, max_capacity=100, can_accept=False)

    # ── Worker summary (heartbeats за последние 90 секунд) ──
    workers_summary: WorkerSummaryResponse | None = None
    try:
        cutoff = datetime.now(timezone.utc)
        # Берём все heartbeats — фильтрация активных в Python
        hb_result = (
            sb.table("worker_heartbeats")
            .select("*")
            .order("last_seen_at", desc=True)
            .limit(50)
            .execute()
        )
        worker_list = []
        for row in hb_result.data or []:
            worker_list.append(WorkerHeartbeatResponse(
                worker_name=row["worker_name"],
                queue_name=row.get("queue_name"),
                host=row.get("host"),
                pid=row.get("pid"),
                memory_mb=row.get("memory_mb"),
                active_tasks=row.get("active_tasks", 0),
                last_seen_at=row["last_seen_at"],
            ))
        workers_summary = WorkerSummaryResponse(
            active_count=len(worker_list),
            workers=worker_list,
        )
    except Exception:
        workers_summary = WorkerSummaryResponse(active_count=0, workers=[])

    return AdminHealthResponse(
        services=services,
        overall=overall,
        queue=queue,
        workers=workers_summary,
    )


@router.get("/events", response_model=SystemEventListResponse)
def admin_events(
    user: CurrentUser = Depends(require_admin),
    severity: str | None = Query(None, description="Фильтр по severity"),
    source_service: str | None = Query(None, description="Фильтр по source_service"),
    event_type: str | None = Query(None, description="Фильтр по event_type"),
    date_from: str | None = Query(None, description="ISO 8601 datetime"),
    date_to: str | None = Query(None, description="ISO 8601 datetime"),
    run_id: str | None = Query(None, description="Фильтр по payload_json.run_id"),
    document_id: str | None = Query(None, description="Фильтр по payload_json.document_id"),
    block_id: str | None = Query(None, description="Фильтр по payload_json.block_id"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> SystemEventListResponse:
    """Список system events с фильтрами. Только для admin."""
    sb = get_supabase()

    # Общее количество (без payload фильтров — они применяются пост-фактум)
    count_query = sb.table("system_events").select("id", count="exact")
    if severity:
        count_query = count_query.eq("severity", severity)
    if source_service:
        count_query = count_query.eq("source_service", source_service)
    if event_type:
        count_query = count_query.eq("event_type", event_type)
    if date_from:
        count_query = count_query.gte("created_at", date_from)
    if date_to:
        count_query = count_query.lte("created_at", date_to)

    # JSONB фильтры через contains
    payload_filter: dict = {}
    if run_id:
        payload_filter["run_id"] = run_id
    if document_id:
        payload_filter["document_id"] = document_id
    if block_id:
        payload_filter["block_id"] = block_id
    if payload_filter:
        count_query = count_query.contains("payload_json", payload_filter)

    count_result = count_query.execute()
    total = count_result.count or 0

    # Данные с пагинацией
    query = (
        sb.table("system_events")
        .select("*")
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if severity:
        query = query.eq("severity", severity)
    if source_service:
        query = query.eq("source_service", source_service)
    if event_type:
        query = query.eq("event_type", event_type)
    if date_from:
        query = query.gte("created_at", date_from)
    if date_to:
        query = query.lte("created_at", date_to)
    if payload_filter:
        query = query.contains("payload_json", payload_filter)

    result = query.execute()

    events = [
        SystemEventResponse(
            id=row["id"],
            event_type=row["event_type"],
            severity=row["severity"],
            source_service=row.get("source_service"),
            payload_json=row.get("payload_json") or {},
            created_at=row["created_at"],
        )
        for row in result.data or []
    ]

    return SystemEventListResponse(
        events=events,
        meta=PaginatedMeta(total=total, limit=limit, offset=offset),
    )
