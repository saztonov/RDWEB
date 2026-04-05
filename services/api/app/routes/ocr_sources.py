"""API endpoints для OCR sources.

Ключевое: credentials_json НЕ включается в ответы.
Dropdown моделей строится из ocr_source_models_cache.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from contracts import (
    OcrSourceListResponse,
    OcrSourceModelResponse,
    OcrSourceModelsListResponse,
    OcrSourceResponse,
)

from ..auth import CurrentUser
from ..auth.dependencies import get_current_user
from ..auth.supabase_client import get_supabase

router = APIRouter(prefix="/ocr/sources", tags=["ocr-sources"])

# Колонки для SELECT — БЕЗ credentials_json
_SOURCE_COLUMNS = (
    "id, source_type, name, base_url, deployment_mode, "
    "is_enabled, concurrency_limit, timeout_sec, "
    "health_status, last_health_at, capabilities_json, "
    "created_at, updated_at"
)


@router.get("", response_model=OcrSourceListResponse)
def list_sources(
    user: CurrentUser = Depends(get_current_user),
) -> OcrSourceListResponse:
    """Список OCR source-ов (без credentials). Для dropdown в UI."""
    sb = get_supabase()
    result = (
        sb.table("ocr_sources")
        .select(_SOURCE_COLUMNS)
        .eq("is_enabled", True)
        .order("name")
        .execute()
    )

    sources = [
        OcrSourceResponse(
            id=row["id"],
            source_type=row["source_type"],
            name=row["name"],
            base_url=row["base_url"],
            deployment_mode=row["deployment_mode"],
            is_enabled=row["is_enabled"],
            concurrency_limit=row["concurrency_limit"],
            timeout_sec=row["timeout_sec"],
            health_status=row["health_status"],
            last_health_at=row.get("last_health_at"),
            capabilities_json=row.get("capabilities_json") or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in result.data or []
    ]

    return OcrSourceListResponse(sources=sources)


@router.get("/{source_id}", response_model=OcrSourceResponse)
def get_source(
    source_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> OcrSourceResponse:
    """Детали OCR source-а (без credentials)."""
    sb = get_supabase()
    result = (
        sb.table("ocr_sources")
        .select(_SOURCE_COLUMNS)
        .eq("id", source_id)
        .maybe_single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="OCR source не найден")

    row = result.data
    return OcrSourceResponse(
        id=row["id"],
        source_type=row["source_type"],
        name=row["name"],
        base_url=row["base_url"],
        deployment_mode=row["deployment_mode"],
        is_enabled=row["is_enabled"],
        concurrency_limit=row["concurrency_limit"],
        timeout_sec=row["timeout_sec"],
        health_status=row["health_status"],
        last_health_at=row.get("last_health_at"),
        capabilities_json=row.get("capabilities_json") or {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.get("/{source_id}/models", response_model=OcrSourceModelsListResponse)
def list_source_models(
    source_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> OcrSourceModelsListResponse:
    """Список моделей source-а из кэша. Для dropdown в UI."""
    sb = get_supabase()

    # Проверяем что source существует
    source_check = (
        sb.table("ocr_sources")
        .select("id")
        .eq("id", source_id)
        .maybe_single()
        .execute()
    )
    if not source_check.data:
        raise HTTPException(status_code=404, detail="OCR source не найден")

    result = (
        sb.table("ocr_source_models_cache")
        .select("model_id, model_name, context_length, supports_vision, fetched_at")
        .eq("source_id", source_id)
        .order("model_name")
        .execute()
    )

    models = [
        OcrSourceModelResponse(
            model_id=row["model_id"],
            model_name=row["model_name"],
            context_length=row.get("context_length"),
            supports_vision=row.get("supports_vision", False),
            fetched_at=row["fetched_at"],
        )
        for row in result.data or []
    ]

    return OcrSourceModelsListResponse(source_id=source_id, models=models)
