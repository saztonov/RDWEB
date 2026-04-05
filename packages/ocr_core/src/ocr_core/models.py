"""Базовые модели OCR ядра.

Block kinds: text, stamp, image.
Тип table удалён полностью — ни в enum, ни в БД, ни в API, ни в UI.
"""

from __future__ import annotations

from enum import StrEnum


class BlockKind(StrEnum):
    """Тип блока на странице документа."""

    TEXT = "text"
    STAMP = "stamp"
    IMAGE = "image"


class ShapeType(StrEnum):
    """Форма выделения блока."""

    RECTANGLE = "rectangle"
    POLYGON = "polygon"


class BlockStatus(StrEnum):
    """Статус блока — совпадает с CHECK constraint в blocks.current_status."""

    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    RECOGNIZED = "recognized"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"
    SKIPPED = "skipped"


class AttemptStatus(StrEnum):
    """Статус попытки распознавания — recognition_attempts.status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class CropUploadState(StrEnum):
    """Состояние загрузки crop в R2."""

    NONE = "none"
    PENDING = "pending"
    UPLOADED = "uploaded"
    FAILED = "failed"


class VerificationCode(StrEnum):
    """Код результата verification OCR-результата."""

    OK = "ok"
    EMPTY = "empty"
    API_ERROR = "api_error"
    SUSPICIOUS_OUTPUT = "suspicious_output"
    PARSER_ERROR = "parser_error"
    INVALID_STAMP_JSON = "invalid_stamp_json"
    INVALID_IMAGE_JSON = "invalid_image_json"
    TOO_SHORT = "too_short"
    GARBAGE_OUTPUT = "garbage_output"
