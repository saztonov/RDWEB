"""Page processor — оркестрация блоков одной страницы.

Открывает PDF один раз, рендерит page_image, итерирует блоки,
вызывает BlockRecognizer для каждого, обновляет run counters.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image
from supabase import Client

from ocr_core import CircuitBreakerRegistry
from ocr_core.models import BlockStatus, CropUploadState

from ..config import get_worker_settings
from ..infra.memory_utils import force_gc, get_pil_image_size_mb, log_memory, log_memory_delta
from ..verification.verifier import Verifier
from .block_recognizer import BlockRecognizer, RecognitionResult
from .prompt_resolver import PromptResolver
from .route_resolver import RouteResolver
from .workspace import Workspace

logger = logging.getLogger(__name__)

# Максимальный размер пикселей для рендеринга (защита от OOM)
_MAX_IMAGE_PIXELS = 500_000_000


@dataclass
class PageResult:
    """Итоги обработки одной страницы."""

    page_number: int
    total_blocks: int = 0
    recognized: int = 0
    failed: int = 0
    manual_review: int = 0
    skipped: int = 0
    block_results: list[RecognitionResult] = field(default_factory=list)


class PageProcessor:
    """Обработка всех блоков одной страницы документа."""

    def __init__(
        self,
        run_id: str,
        document_id: str,
        page_number: int,
        block_ids: list[str],
        pdf_path: Path,
        db: Client,
    ) -> None:
        self._run_id = run_id
        self._document_id = document_id
        self._page_number = page_number
        self._block_ids = block_ids
        self._pdf_path = pdf_path
        self._db = db

    def process(self) -> PageResult:
        """Основ��ой метод — обработка всех блоков страницы."""
        settings = get_worker_settings()
        result = PageResult(page_number=self._page_number, total_blocks=len(self._block_ids))

        # Загрузить document metadata для profile_id и title
        doc = self._load_document()
        document_profile_id = doc.get("document_profile_id")
        if not document_profile_id:
            logger.error(
                "Document %s не имеет document_profile_id, skip page %d",
                self._document_id, self._page_number,
            )
            return result

        # Создать workspace
        workspace = Workspace(settings.workspace_base_dir, self._run_id, self._page_number)
        workspace.ensure_dirs(self._block_ids)

        # Shared dependencies
        circuit_breakers = CircuitBreakerRegistry()
        route_resolver = RouteResolver(self._db)
        prompt_resolver = PromptResolver(self._db)
        verifier = Verifier()
        recognizer = BlockRecognizer(
            run_id=self._run_id,
            document_id=self._document_id,
            document_profile_id=document_profile_id,
            db=self._db,
            route_resolver=route_resolver,
            prompt_resolver=prompt_resolver,
            verifier=verifier,
            circuit_breakers=circuit_breakers,
            max_retries=settings.max_retries_same_model,
        )

        start_mem = log_memory(f"page_{self._page_number}_start")

        try:
            # Открыть PDF и отрендерить страницу
            page_image = self._render_page(settings)
            logger.info(
                "Page %d rendered: %dx%d (%.1f MB RAM)",
                self._page_number,
                page_image.width, page_image.height,
                get_pil_image_size_mb(page_image),
            )

            # Обработать каждый блок
            for block_id in self._block_ids:
                block_data = self._load_block(block_id)
                if not block_data:
                    logger.warning("Block %s not found, skipping", block_id)
                    continue

                # Пропустить locked / deleted / already recognized
                if block_data.get("manual_lock"):
                    result.skipped += 1
                    continue
                if block_data.get("deleted_at"):
                    result.skipped += 1
                    continue

                # Обновить статус на processing
                self._update_block_status(block_id, BlockStatus.PROCESSING)

                # Распознать блок
                try:
                    block_result = recognizer.recognize(
                        block_data, page_image, workspace,
                        doc_name=doc.get("title", ""),
                    )
                except Exception as exc:
                    logger.error("Block %s recognition crashed: %s", block_id, exc, exc_info=True)
                    self._update_block_status(block_id, BlockStatus.FAILED)
                    block_result = RecognitionResult(
                        block_id=block_id,
                        terminal_status=BlockStatus.FAILED,
                        error_code="recognition_crash",
                    )

                result.block_results.append(block_result)
                self._count_result(result, block_result)

                # Обновить run counters (инкрементально)
                self._increment_run_counter(block_result)

            # Освободить page_image
            del page_image
            force_gc(f"page_{self._page_number}_done")

        finally:
            log_memory_delta(f"page_{self._page_number}_end", start_mem)
            # НЕ чистим workspace здесь — crop файлы нужны для upload_crop_task
            # workspace.cleanup() вызывается из task после dispatch upload

        return result

    # ── Приватные методы ─────────────────────────────────────────────

    def _render_page(self, settings) -> Image.Image:
        """Открыть PDF и отрендерить одну страницу в PIL Image."""
        doc = fitz.open(str(self._pdf_path))
        try:
            page_idx = self._page_number - 1  # 0-based
            if page_idx < 0 or page_idx >= len(doc):
                raise ValueError(
                    f"Page {self._page_number} out of range (total={len(doc)})"
                )

            page = doc[page_idx]

            # Рассчитать zoom с учётом лимита пикселей
            zoom = self._calculate_zoom(page, settings.default_dpi, _MAX_IMAGE_PIXELS)
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)

            # Direct pixmap → PIL (без промежуточного PNG)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            return img
        finally:
            doc.close()

    @staticmethod
    def _calculate_zoom(page, target_dpi: int, max_pixels: int) -> float:
        """Рассчитать zoom factor для рендеринга страницы.

        Адаптация из legacy StreamingPDFProcessor.get_effective_zoom().
        """
        zoom = target_dpi / 72.0  # fitz использует 72 DPI по умолчанию
        rect = page.rect
        w = rect.width * zoom
        h = rect.height * zoom
        pixels = w * h

        if pixels > max_pixels:
            scale = (max_pixels / pixels) ** 0.5
            zoom *= scale

        return zoom

    def _load_document(self) -> dict:
        """Загрузить document из БД."""
        result = (
            self._db.table("documents")
            .select("id, title, document_profile_id")
            .eq("id", self._document_id)
            .single()
            .execute()
        )
        return result.data

    def _load_block(self, block_id: str) -> dict | None:
        """Загрузить блок из БД."""
        result = (
            self._db.table("blocks")
            .select("*")
            .eq("id", block_id)
            .maybe_single()
            .execute()
        )
        return result.data

    def _update_block_status(self, block_id: str, status: str) -> None:
        """Обновить current_status блока."""
        self._db.table("blocks").update({
            "current_status": status,
        }).eq("id", block_id).execute()

    def _increment_run_counter(self, block_result: RecognitionResult) -> None:
        """Инкрементально обновить счётчики recognition_run.

        Используем RPC для атомарного инкремента.
        """
        if block_result.skipped:
            return

        update: dict = {"processed_blocks": "processed_blocks + 1"}
        if block_result.terminal_status == BlockStatus.RECOGNIZED:
            field = "recognized_blocks"
        elif block_result.terminal_status == BlockStatus.MANUAL_REVIEW:
            field = "manual_review_blocks"
        else:
            field = "failed_blocks"

        # Supabase Python SDK не поддерживает SQL expression в update,
        # поэтому читаем-пишем (acceptable для MVP, race condition маловероятен)
        run_result = (
            self._db.table("recognition_runs")
            .select("processed_blocks, recognized_blocks, failed_blocks, manual_review_blocks")
            .eq("id", self._run_id)
            .single()
            .execute()
        )
        run = run_result.data
        self._db.table("recognition_runs").update({
            "processed_blocks": run["processed_blocks"] + 1,
            field: run[field] + 1,
        }).eq("id", self._run_id).execute()

    @staticmethod
    def _count_result(result: PageResult, block_result: RecognitionResult) -> None:
        """Подсчитать итоги для PageResult."""
        if block_result.skipped:
            result.skipped += 1
        elif block_result.terminal_status == BlockStatus.RECOGNIZED:
            result.recognized += 1
        elif block_result.terminal_status == BlockStatus.MANUAL_REVIEW:
            result.manual_review += 1
        else:
            result.failed += 1
