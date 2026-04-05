"""OCR Core — ядро OCR системы."""

from .circuit_breaker import CircuitBreaker, CircuitBreakerRegistry, CircuitOpenError, CircuitState
from .models import (
    AttemptStatus,
    BlockKind,
    BlockStatus,
    CropUploadState,
    ShapeType,
    VerificationCode,
)
from .pdf_cache import PdfCacheManager
from .provider import OcrProvider
from .provider_factory import create_provider
from .provider_types import (
    DeploymentMode,
    HealthResult,
    HealthStatus,
    ModelInfo,
    RecognizeResult,
    SourceConfig,
    SourceType,
)

__all__ = [
    # Модели
    "AttemptStatus",
    "BlockKind",
    "BlockStatus",
    "CropUploadState",
    "ShapeType",
    "VerificationCode",
    # PDF
    "PdfCacheManager",
    # Провайдеры
    "OcrProvider",
    "create_provider",
    # Типы провайдеров
    "SourceType",
    "DeploymentMode",
    "HealthStatus",
    "SourceConfig",
    "HealthResult",
    "ModelInfo",
    "RecognizeResult",
    # Circuit breaker
    "CircuitBreaker",
    "CircuitBreakerRegistry",
    "CircuitOpenError",
    "CircuitState",
]
