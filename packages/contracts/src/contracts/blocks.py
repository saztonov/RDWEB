"""Schemas для блоков. Block kinds: text, stamp, image — БЕЗ table."""

from __future__ import annotations

from pydantic import BaseModel

from ocr_core.models import BlockKind, ShapeType


class BlockCoords(BaseModel):
    """Координаты блока на странице."""

    x: float
    y: float
    width: float
    height: float


class BlockBase(BaseModel):
    """Базовая схема блока."""

    kind: BlockKind
    shape_type: ShapeType = ShapeType.RECTANGLE
    coords: BlockCoords
    polygon_points: list[tuple[float, float]] | None = None


class TextBlock(BlockBase):
    """Текстовый блок с результатом OCR."""

    kind: BlockKind = BlockKind.TEXT
    ocr_text: str | None = None
    manual_text: str | None = None
    is_dirty: bool = False


class StampBlock(BlockBase):
    """Блок печати/штампа."""

    kind: BlockKind = BlockKind.STAMP
    ocr_text: str | None = None


class ImageBlock(BlockBase):
    """Блок изображения."""

    kind: BlockKind = BlockKind.IMAGE
    crop_url: str | None = None
