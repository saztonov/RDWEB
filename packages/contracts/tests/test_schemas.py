"""Тесты для shared schemas."""

from contracts.health import HealthResponse, ReadinessResponse
from contracts.blocks import TextBlock, StampBlock, ImageBlock, BlockCoords
from ocr_core.models import BlockKind


def test_health_response():
    resp = HealthResponse(ok=True)
    assert resp.ok is True


def test_readiness_response():
    resp = ReadinessResponse(
        ready=False,
        checks={"redis": True, "supabase": False, "config": True},
    )
    assert resp.ready is False
    assert resp.checks.redis is True


def test_text_block():
    block = TextBlock(
        coords=BlockCoords(x=0, y=0, width=100, height=50),
        ocr_text="Hello",
    )
    assert block.kind == BlockKind.TEXT
    assert block.ocr_text == "Hello"
    assert block.is_dirty is False


def test_stamp_block():
    block = StampBlock(
        coords=BlockCoords(x=10, y=20, width=80, height=80),
    )
    assert block.kind == BlockKind.STAMP


def test_image_block():
    block = ImageBlock(
        coords=BlockCoords(x=0, y=0, width=200, height=300),
    )
    assert block.kind == BlockKind.IMAGE


def test_no_table_block_kind():
    """Убеждаемся что table нет в BlockKind."""
    assert "table" not in [e.value for e in BlockKind]
