"""Периодическая синхронизация моделей OCR source-ов.

Для каждого enabled source вызывает list_models() и обновляет ocr_source_models_cache.
Запускается Celery beat каждые 5 минут.
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


async def _sync_one_source(sb: Client, config: SourceConfig) -> int:
    """Синхронизировать модели одного source-а."""
    provider = create_provider(config)
    try:
        models = await provider.list_models()
        now = datetime.now(timezone.utc).isoformat()

        for model in models:
            sb.table("ocr_source_models_cache").upsert(
                {
                    "source_id": config.id,
                    "model_id": model.model_id,
                    "model_name": model.model_name,
                    "context_length": model.context_length,
                    "supports_vision": model.supports_vision,
                    "extra_json": model.extra if model.extra else None,
                    "fetched_at": now,
                },
                on_conflict="source_id,model_id",
            ).execute()

        # Удалить модели, которых больше нет
        current_ids = {m.model_id for m in models}
        existing = (
            sb.table("ocr_source_models_cache")
            .select("id, model_id")
            .eq("source_id", config.id)
            .execute()
        )
        for row in existing.data or []:
            if row["model_id"] not in current_ids:
                sb.table("ocr_source_models_cache").delete().eq("id", row["id"]).execute()

        return len(models)
    finally:
        await provider.close()


@celery_app.task(name="ocr.sync_source_models", ignore_result=True)
def sync_source_models() -> dict:
    """Периодическая синхронизация моделей всех enabled source-ов."""
    settings = get_worker_settings()
    if not settings.supabase_url or not settings.supabase_key:
        logger.warning("sync_source_models: Supabase не настроен")
        return {"status": "skipped", "reason": "no_supabase"}

    sb = _get_supabase()
    result = (
        sb.table("ocr_sources")
        .select("*")
        .eq("is_enabled", True)
        .execute()
    )

    sources = result.data or []
    synced: dict[str, int] = {}
    errors: dict[str, str] = {}

    for row in sources:
        config = _row_to_config(row)
        try:
            count = asyncio.run(_sync_one_source(sb, config))
            synced[config.name] = count
            logger.info("Model sync: '%s' → %d моделей", config.name, count)
        except Exception as exc:
            errors[config.name] = str(exc)
            logger.error("Model sync failed для '%s': %s", config.name, exc)

    return {"synced": synced, "errors": errors}
