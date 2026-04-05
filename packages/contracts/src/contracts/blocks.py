"""Schemas для блоков. Block kinds: text, stamp, image — БЕЗ table.

Включает request/response для manual edit, lock, attempts, recognition runs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ocr_core.models import BlockKind, ShapeType


# ──────────────────────────────────────────────────────────────────────
# Базовые модели блоков
# ──────────────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────────────
# Requests — manual edit, lock, rerun, accept, recognition
# ──────────────────────────────────────────────────────────────────────

class ManualEditRequest(BaseModel):
    """Ручная правка текста / structured_json блока."""
    current_text: str | None = None
    current_structured_json: dict | None = None


class ToggleLockRequest(BaseModel):
    """Переключение manual_lock."""
    manual_lock: bool


class RerunBlockRequest(BaseModel):
    """Перезапуск распознавания одного блока."""
    force: bool = Field(False, description="Игнорировать manual_lock и запустить rerun")


class AcceptAttemptRequest(BaseModel):
    """Принятие candidate attempt как текущего результата."""
    attempt_id: str


class RecognitionRunCreateRequest(BaseModel):
    """Запуск recognition run."""
    run_mode: str = Field(..., pattern=r"^(smart|full|block_rerun)$")
    block_ids: list[str] | None = None


# ──────────────────────────────────────────────────────────────────────
# Responses — attempts, dirty summary, recognition runs
# ──────────────────────────────────────────────────────────────────────

class RecognitionAttemptResponse(BaseModel):
    """Одна попытка распознавания."""
    id: str
    run_id: str | None = None
    block_id: str
    geometry_rev: int | None = None
    source_id: str | None = None
    model_name: str | None = None
    prompt_template_id: str | None = None
    attempt_no: int | None = None
    fallback_no: int = 0
    status: str
    normalized_text: str | None = None
    structured_json: dict | None = None
    render_html: str | None = None
    quality_flags_json: dict | None = None
    error_code: str | None = None
    error_message: str | None = None
    selected_as_current: bool = False
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str


class RecognitionAttemptListResponse(BaseModel):
    """Список попыток распознавания блока."""
    attempts: list[RecognitionAttemptResponse]


class DirtyBlocksSummaryResponse(BaseModel):
    """Сводка dirty-блоков документа."""
    total: int
    dirty_count: int
    locked_count: int
    dirty_block_ids: list[str]


class RecognitionRunResponse(BaseModel):
    """Статус recognition run."""
    id: str
    document_id: str
    initiated_by: str | None = None
    run_mode: str
    status: str
    total_blocks: int
    dirty_blocks: int
    processed_blocks: int
    recognized_blocks: int
    failed_blocks: int
    manual_review_blocks: int
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str


class RecognitionRunListResponse(BaseModel):
    """Список recognition runs."""
    runs: list[RecognitionRunResponse]


class BlockDetailResponse(BaseModel):
    """Полная информация о блоке с provenance."""
    block: dict
    current_attempt: dict | None = None
    attempts_count: int = 0
    pending_candidate: dict | None = None
