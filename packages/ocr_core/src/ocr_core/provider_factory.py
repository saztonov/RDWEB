"""Фабрика OCR-провайдеров.

Создаёт конкретный провайдер по SourceConfig из БД.
"""

from __future__ import annotations

from .provider import OcrProvider
from .provider_types import SourceConfig, SourceType
from .providers.lmstudio import LmStudioProvider
from .providers.openrouter import OpenRouterProvider

_REGISTRY: dict[SourceType, type[OcrProvider]] = {
    SourceType.OPENROUTER: OpenRouterProvider,
    SourceType.LMSTUDIO: LmStudioProvider,
}


def create_provider(config: SourceConfig) -> OcrProvider:
    """Создать провайдер по конфигурации source-а из БД."""
    cls = _REGISTRY.get(config.source_type)
    if cls is None:
        raise ValueError(f"Неизвестный source_type: {config.source_type}")
    return cls(config)
