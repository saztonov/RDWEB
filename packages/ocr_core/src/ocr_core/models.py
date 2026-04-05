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
