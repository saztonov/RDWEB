"""Периодический healthcheck OCR source-ов.

Для каждого enabled source вызывает healthcheck() и обновляет:
- service_health_checks (INSERT)
- ocr_sources.health_status + last_health_at (UPDATE)

Запускается Celery beat каждую минуту.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from ocr_core import SourceConfig, SourceType, create_provider
from ocr_core.provider_types import DeploymentMode
from supabase import Client, create_client

from ..celery_app import celery_app
from ..config import get_worker_settings

logger = logging.getLogger(__name__)


def _get_supabase() -> Client:
    """Создать Supabase client для worker context."""
    settings = get_worker_settings()
    return create_client(settings.supabase_url, settings.supabase_key)


def _row_to_config(row: dict) -> SourceConfig:
    """Конвертация строки БД в SourceConfig."""
    return SourceConfig(
        id=row["id"],
        source_type=SourceType(row["source_type"]),
        name=row["name"],
        base_url=row["base_url"],
        deployment_mode=DeploymentMode(row["deployment_mode"]),
        credentials=row.get("credentials_json") or {},
        concurrency_limit=row.get("concurrency_limit", 4),
        timeout_sec=row.get("timeout_sec", 120),
        capabilities=row.get("capabilities_json") or {},
    )


async def _probe_one_source(sb: Client, config: SourceConfig) -> str:
    """Healthcheck одного source-а, запись в БД."""
    provider = create_provider(config)
    try:
        result = await provider.healthcheck()
        now = datetime.now(timezone.utc).isoformat()

        # INSERT в service_health_checks
        sb.table("service_health_checks").insert({
            "service_name": f"ocr_source:{config.name}",
            "status": result.status.value,
            "response_time_ms": result.response_time_ms,
            "details_json": result.details,
            "checked_at": now,
        }).execute()

        # UPDATE ocr_sources
        sb.table("ocr_sources").update({
            "health_status": result.status.value,
            "last_health_at": now,
        }).eq("id", config.id).execute()

        return result.status.value
    finally:
        await provider.close()


@celery_app.task(name="ocr.probe_source_health", ignore_result=True)
def probe_source_health() -> dict:
    """Периодический healthcheck всех enabled source-ов."""
    settings = get_worker_settings()
    if not settings.supabase_url or not settings.supabase_key:
        logger.warning("probe_source_health: Supabase не настроен")
        return {"status": "skipped", "reason": "no_supabase"}

    sb = _get_supabase()
    result = (
        sb.table("ocr_sources")
        .select("*")
        .eq("is_enabled", True)
        .execute()
    )

    sources = result.data or []
    results: dict[str, str] = {}
    errors: dict[str, str] = {}

    for row in sources:
        config = _row_to_config(row)
        try:
            status = asyncio.run(_probe_one_source(sb, config))
            results[config.name] = status
            logger.info("Health probe: '%s' → %s", config.name, status)
        except Exception as exc:
            errors[config.name] = str(exc)
            logger.error("Health probe failed для '%s': %s", config.name, exc)

            # Записываем unavailable при ошибке
            try:
                now = datetime.now(timezone.utc).isoformat()
                sb.table("service_health_checks").insert({
                    "service_name": f"ocr_source:{config.name}",
                    "status": "unavailable",
                    "details_json": {"error": str(exc)},
                    "checked_at": now,
                }).execute()
                sb.table("ocr_sources").update({
                    "health_status": "unavailable",
                    "last_health_at": now,
                }).eq("id", config.id).execute()
            except Exception:
                pass

    return {"results": results, "errors": errors}
