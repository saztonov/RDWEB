"""Admin endpoints для OCR sources — расширенная информация, healthcheck, sync."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from contracts import (
    AdminOcrSourceDetailResponse,
    AdminOcrSourceListResponse,
    AdminOcrSourceResponse,
    HealthCheckResponse,
    ServiceHealthResponse,
)

from ..auth import CurrentUser, get_supabase
from ..auth.dependencies import require_admin

router = APIRouter(prefix="/admin/ocr", tags=["admin-sources"])


def _build_source_response(row: dict, health_info: dict | None = None, models_count: int = 0) -> AdminOcrSourceResponse:
    """Собрать AdminOcrSourceResponse из строки БД + health."""
    last_error = None
    last_response_time_ms = None

    if health_info:
        last_response_time_ms = health_info.get("response_time_ms")
        details = health_info.get("details_json") or {}
        if isinstance(details, dict):
            last_error = details.get("error")

    return AdminOcrSourceResponse(
        id=row["id"],
        source_type=row["source_type"],
        name=row["name"],
        base_url=row.get("base_url"),
        deployment_mode=row.get("deployment_mode"),
        is_enabled=row.get("is_enabled", True),
        concurrency_limit=row.get("concurrency_limit", 4),
        timeout_sec=row.get("timeout_sec", 120),
        health_status=row.get("health_status", "unknown"),
        last_health_at=row.get("last_health_at"),
        capabilities_json=row.get("capabilities_json") or {},
        last_error=last_error,
        last_response_time_ms=last_response_time_ms,
        cached_models_count=models_count,
    )


@router.get("/sources", response_model=AdminOcrSourceListResponse)
def admin_list_sources(user: CurrentUser = Depends(require_admin)) -> AdminOcrSourceListResponse:
    """Список всех OCR sources (включая disabled) с расширенной информацией."""
    sb = get_supabase()

    # Все sources
    sources_result = sb.table("ocr_sources").select("*").order("name").execute()
    sources = sources_result.data or []

    # Последние health checks для каждого source
    health_result = (
        sb.table("service_health_checks")
        .select("*")
        .like("service_name", "ocr_source:%")
        .order("checked_at", desc=True)
        .limit(100)
        .execute()
    )
    # Дедупликация по service_name
    health_map: dict[str, dict] = {}
    for row in health_result.data or []:
        name = row["service_name"]
        if name not in health_map:
            health_map[name] = row

    # Количество cached models для каждого source
    models_result = (
        sb.table("ocr_source_models_cache")
        .select("source_id, id")
        .execute()
    )
    models_counts: dict[str, int] = {}
    for row in models_result.data or []:
        sid = row["source_id"]
        models_counts[sid] = models_counts.get(sid, 0) + 1

    items = []
    for src in sources:
        health_key = f"ocr_source:{src['name']}"
        health_info = health_map.get(health_key)
        items.append(_build_source_response(src, health_info, models_counts.get(src["id"], 0)))

    return AdminOcrSourceListResponse(sources=items)


@router.get("/sources/{source_id}", response_model=AdminOcrSourceDetailResponse)
def admin_source_detail(
    source_id: str,
    user: CurrentUser = Depends(require_admin),
) -> AdminOcrSourceDetailResponse:
    """Детальная информация об OCR source: модели + история health checks."""
    sb = get_supabase()

    # Source
    source_result = sb.table("ocr_sources").select("*").eq("id", source_id).maybe_single().execute()
    if not source_result.data:
        raise HTTPException(status_code=404, detail="OCR source не найден")

    src = source_result.data

    # Cached models
    models_result = (
        sb.table("ocr_source_models_cache")
        .select("*")
        .eq("source_id", source_id)
        .order("model_name")
        .execute()
    )
    cached_models = models_result.data or []

    # Последние 10 health checks
    health_name = f"ocr_source:{src['name']}"
    health_result = (
        sb.table("service_health_checks")
        .select("*")
        .eq("service_name", health_name)
        .order("checked_at", desc=True)
        .limit(10)
        .execute()
    )
    recent_checks = [
        ServiceHealthResponse(
            service_name=row["service_name"],
            status=row["status"],
            response_time_ms=row.get("response_time_ms"),
            details_json=row.get("details_json"),
            checked_at=row["checked_at"],
        )
        for row in health_result.data or []
    ]

    # Последняя ошибка
    last_error = None
    last_response_time_ms = None
    if recent_checks:
        last_response_time_ms = recent_checks[0].response_time_ms
        details = recent_checks[0].details_json or {}
        if isinstance(details, dict):
            last_error = details.get("error")

    return AdminOcrSourceDetailResponse(
        id=src["id"],
        source_type=src["source_type"],
        name=src["name"],
        base_url=src.get("base_url"),
        deployment_mode=src.get("deployment_mode"),
        is_enabled=src.get("is_enabled", True),
        concurrency_limit=src.get("concurrency_limit", 4),
        timeout_sec=src.get("timeout_sec", 120),
        health_status=src.get("health_status", "unknown"),
        last_health_at=src.get("last_health_at"),
        capabilities_json=src.get("capabilities_json") or {},
        last_error=last_error,
        last_response_time_ms=last_response_time_ms,
        cached_models_count=len(cached_models),
        recent_health_checks=recent_checks,
        cached_models=cached_models,
    )


@router.post("/sources/{source_id}/healthcheck", response_model=HealthCheckResponse)
async def trigger_healthcheck(
    source_id: str,
    request: Request,
    user: CurrentUser = Depends(require_admin),
) -> HealthCheckResponse:
    """Ручной healthcheck OCR source-а. Только для admin."""
    from ..services.source_registry import SourceRegistry

    registry: SourceRegistry = request.app.state.source_registry

    if not registry.has_source(source_id):
        raise HTTPException(status_code=404, detail="OCR source не найден или отключён")

    result = await registry.run_healthcheck(source_id)
    config = registry.get_config(source_id)

    return HealthCheckResponse(
        source_id=source_id,
        source_name=config.name,
        health_status=result.status.value,
        response_time_ms=result.response_time_ms,
        details=result.details,
        checked_at=datetime.now(timezone.utc),
    )
