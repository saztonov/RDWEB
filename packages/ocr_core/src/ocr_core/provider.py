"""Базовый ABC для OCR-провайдеров.

Определяет контракт: healthcheck, list_models, recognize_block.
Промпты приходят извне — провайдер не хардкодит промпты.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .provider_types import HealthResult, ModelInfo, RecognizeResult, SourceConfig, SourceType


class OcrProvider(ABC):
    """Базовый интерфейс OCR-провайдера.

    Каждый провайдер оборачивает один source из ocr_sources.
    async-first: httpx AsyncClient, worker оборачивает через asyncio.run().
    """

    def __init__(self, config: SourceConfig) -> None:
        self._config = config

    @property
    def source_id(self) -> str:
        return self._config.id

    @property
    def source_type(self) -> SourceType:
        return self._config.source_type

    @property
    def config(self) -> SourceConfig:
        return self._config

    @abstractmethod
    async def healthcheck(self) -> HealthResult:
        """Проверка доступности source-а."""
        ...

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """Получить список доступных моделей."""
        ...

    @abstractmethod
    async def recognize_block(
        self,
        image_b64: str,
        system_prompt: str,
        user_prompt: str,
        model_id: str,
        *,
        max_tokens: int = 16384,
        temperature: float = 0.1,
        response_format: dict[str, Any] | None = None,
    ) -> RecognizeResult:
        """Распознать блок. Промпты приходят извне — не хардкодятся внутри."""
        ...

    async def close(self) -> None:
        """Закрыть httpx client и освободить ресурсы."""
