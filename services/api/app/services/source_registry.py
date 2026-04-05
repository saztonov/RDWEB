"""Реестр OCR source-ов с провайдерами и circuit breaker-ами.

Центральная точка интеграции: загрузка из БД, lifecycle провайдеров,
healthcheck, model sync. Инициализируется в lifespan FastAPI.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from ocr_core import (
    CircuitBreakerRegistry,
    HealthResult,
    HealthStatus,
    OcrProvider,
    SourceConfig,
    SourceType,
    create_provider,
)
from ocr_core.provider_types import DeploymentMode

from ..auth.supabase_client import get_supabase
from ..logging_config import get_logger

logger = get_logger(__name__)


def _row_to_config(row: dict[str, Any]) -> SourceConfig:
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


class SourceRegistry:
    """Реестр активных OCR source-ов.

    Хранит провайдеры и circuit breaker-ы для каждого enabled source-а.
    Per-process: у API и worker свои инстансы.
    """

    def __init__(self) -> None:
        self._providers: dict[str, OcrProvider] = {}
        self._configs: dict[str, SourceConfig] = {}
        self._cb_registry = CircuitBreakerRegistry()
        self._lock = asyncio.Lock()

    @property
    def cb_registry(self) -> CircuitBreakerRegistry:
        return self._cb_registry

    async def load_from_db(self) -> None:
        """Загрузить все enabled source-ы из ocr_sources, создать провайдеры."""
        sb = get_supabase()
        result = (
            sb.table("ocr_sources")
            .select("*")
            .eq("is_enabled", True)
            .execute()
        )

        async with self._lock:
            # Закрываем старые провайдеры
            for provider in self._providers.values():
                try:
                    await provider.close()
                except Exception:
                    pass

            self._providers.clear()
            self._configs.clear()

            for row in result.data or []:
                try:
                    config = _row_to_config(row)
                    provider = create_provider(config)
                    self._providers[config.id] = provider
                    self._configs[config.id] = config

                    # Создаём circuit breaker для source-а
                    self._cb_registry.get_or_create(
                        config.id,
                        service_name=config.name,
                    )
                except Exception as exc:
                    logger.error(
                        "Не удалось создать провайдер для source '%s': %s",
                        row.get("name", row.get("id")),
                        exc,
                    )

        logger.info(
            "SourceRegistry загружен: %d source-ов",
            len(self._providers),
            extra={
                "event": "source_registry_loaded",
                "source_count": len(self._providers),
                "sources": [
                    {"id": c.id, "name": c.name, "type": c.source_type}
                    for c in self._configs.values()
                ],
            },
        )

    async def reload_source(self, source_id: str) -> None:
        """Перезагрузить конкретный source (после admin edit)."""
        sb = get_supabase()
        result = (
            sb.table("ocr_sources")
            .select("*")
            .eq("id", source_id)
            .single()
            .execute()
        )

        if not result.data:
            # Source удалён или не найден — убираем из реестра
            async with self._lock:
                provider = self._providers.pop(source_id, None)
                self._configs.pop(source_id, None)
                self._cb_registry.remove(source_id)
                if provider:
                    await provider.close()
            return

        row = result.data
        config = _row_to_config(row)

        async with self._lock:
            # Закрываем старый провайдер
            old = self._providers.pop(source_id, None)
            if old:
                await old.close()

            if row.get("is_enabled"):
                provider = create_provider(config)
                self._providers[config.id] = provider
                self._configs[config.id] = config
                self._cb_registry.get_or_create(config.id, service_name=config.name)
            else:
                self._configs.pop(source_id, None)
                self._cb_registry.remove(source_id)

    def get_provider(self, source_id: str) -> OcrProvider:
        """Получить провайдер по source_id. Raises KeyError."""
        return self._providers[source_id]

    def get_config(self, source_id: str) -> SourceConfig:
        """Получить конфиг по source_id. Raises KeyError."""
        return self._configs[source_id]

    def list_configs(self) -> list[SourceConfig]:
        """Список конфигов enabled source-ов."""
        return list(self._configs.values())

    def has_source(self, source_id: str) -> bool:
        return source_id in self._providers

    async def run_healthcheck(self, source_id: str) -> HealthResult:
        """Выполнить healthcheck source-а.

        1. Вызвать provider.healthcheck()
        2. Записать в service_health_checks
        3. Обновить ocr_sources.health_status + last_health_at
        4. Обновить circuit breaker
        """
        provider = self.get_provider(source_id)
        config = self.get_config(source_id)
        cb = self._cb_registry.get_or_create(source_id, service_name=config.name)

        result = await provider.healthcheck()
        now = datetime.now(timezone.utc).isoformat()

        # Обновить circuit breaker
        if result.status == HealthStatus.HEALTHY:
            cb.record_success()
        else:
            cb.record_failure()

        # Записать в БД
        sb = get_supabase()

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
        }).eq("id", source_id).execute()

        logger.info(
            "Healthcheck для '%s': %s (%dms)",
            config.name,
            result.status.value,
            result.response_time_ms,
            extra={
                "event": "source_healthcheck",
                "source_id": source_id,
                "status": result.status.value,
                "response_time_ms": result.response_time_ms,
            },
        )

        return result

    async def sync_models(self, source_id: str) -> int:
        """Синхронизировать модели source-а в ocr_source_models_cache.

        1. Вызвать provider.list_models()
        2. UPSERT в ocr_source_models_cache
        3. Удалить модели, отсутствующие в ответе
        """
        provider = self.get_provider(source_id)
        config = self.get_config(source_id)

        models = await provider.list_models()
        now = datetime.now(timezone.utc).isoformat()

        sb = get_supabase()

        # UPSERT каждой модели
        for model in models:
            sb.table("ocr_source_models_cache").upsert(
                {
                    "source_id": source_id,
                    "model_id": model.model_id,
                    "model_name": model.model_name,
                    "context_length": model.context_length,
                    "supports_vision": model.supports_vision,
                    "extra_json": model.extra if model.extra else None,
                    "fetched_at": now,
                },
                on_conflict="source_id,model_id",
            ).execute()

        # Удалить модели, которых больше нет у провайдера
        current_model_ids = {m.model_id for m in models}
        existing = (
            sb.table("ocr_source_models_cache")
            .select("id, model_id")
            .eq("source_id", source_id)
            .execute()
        )

        for row in existing.data or []:
            if row["model_id"] not in current_model_ids:
                sb.table("ocr_source_models_cache").delete().eq("id", row["id"]).execute()

        logger.info(
            "Model sync для '%s': %d моделей",
            config.name,
            len(models),
            extra={
                "event": "source_model_sync",
                "source_id": source_id,
                "model_count": len(models),
            },
        )

        return len(models)

    async def close_all(self) -> None:
        """Закрыть все httpx clients при shutdown."""
        async with self._lock:
            for provider in self._providers.values():
                try:
                    await provider.close()
                except Exception:
                    pass
            self._providers.clear()
            self._configs.clear()
