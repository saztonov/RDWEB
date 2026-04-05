"""Admin endpoints — health и events. Доступны только global admin."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from contracts import (
    AdminHealthResponse,
    PaginatedMeta,
    ServiceHealthResponse,
    SystemEventListResponse,
    SystemEventResponse,
)

from ..auth import CurrentUser, get_supabase
from ..auth.dependencies import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/health", response_model=AdminHealthResponse)
def admin_health(user: CurrentUser = Depends(require_admin)) -> AdminHealthResponse:
    """Health-статус всех сервисов. Только для admin."""
    sb = get_supabase()

    # Последний health check для каждого сервиса
    # Supabase не поддерживает DISTINCT ON, берём последние N записей и дедуплицируем
    result = (
        sb.table("service_health_checks")
        .select("*")
        .order("checked_at", desc=True)
        .limit(100)
        .execute()
    )

    # Дедупликация: оставляем только последний check для каждого service_name
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
            checked_at=row["checked_at"],
        )
        for row in seen.values()
    ]

    # Определить overall status
    statuses = {s.status for s in services}
    if not services:
        overall = "unknown"
    elif "unavailable" in statuses:
        overall = "unavailable"
    elif "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "healthy"

    return AdminHealthResponse(services=services, overall=overall)


@router.get("/events", response_model=SystemEventListResponse)
def admin_events(
    user: CurrentUser = Depends(require_admin),
    severity: str | None = Query(None, description="Фильтр по severity (info/warning/error/critical)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> SystemEventListResponse:
    """Список system events с пагинацией. Только для admin."""
    sb = get_supabase()

    # Общее количество
    query = sb.table("system_events").select("id", count="exact")
    if severity:
        query = query.eq("severity", severity)
    count_result = query.execute()
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
