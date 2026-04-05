"""Тесты для базовых моделей OCR ядра."""

from ocr_core.models import BlockKind, ShapeType


def test_block_kind_values():
    """BlockKind содержит ровно три значения: text, stamp, image."""
    assert set(BlockKind) == {BlockKind.TEXT, BlockKind.STAMP, BlockKind.IMAGE}
    assert len(BlockKind) == 3


def test_block_kind_no_table():
    """Тип table удалён полностью."""
    values = {e.value for e in BlockKind}
    assert "table" not in values


def test_block_kind_str():
    """BlockKind можно использовать как строку."""
    assert BlockKind.TEXT == "text"
    assert BlockKind.STAMP == "stamp"
    assert BlockKind.IMAGE == "image"


def test_shape_type_values():
    assert set(ShapeType) == {ShapeType.RECTANGLE, ShapeType.POLYGON}
