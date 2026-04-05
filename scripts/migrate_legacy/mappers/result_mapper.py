"""Маппинг legacy result.json → recognition_attempts + обогащение blocks.

result.json содержит объединённые данные:
- ocr_html — HTML фрагмент распознанного текста
- ocr_json — parsed structured data (для IMAGE/STAMP)
- ocr_meta — метаданные (method, match_score)
- crop_url — ссылка на кроп в R2

ВАЖНО: result.json НЕ используется как source of truth.
Он используется только для извлечения render_html, structured_json и quality_flags.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional
from urllib.parse import urlparse

from ..utils import is_ocr_error, is_ocr_success, new_uuid, now_utc

logger = logging.getLogger("migrate_legacy.result_mapper")


def parse_result_json(raw: Any) -> dict:
    """Распарсить result.json (может быть строкой или dict)."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error("Не удалось распарсить result.json")
            return {}
    return raw if isinstance(raw, dict) else {}


def build_block_index(result_data: dict) -> dict[str, dict]:
    """Построить индекс block_id → block_data из result.json.

    result.json имеет page_number 1-based (после merge).
    Сопоставление идёт по block ID, не по позиции.
    """
    index: dict[str, dict] = {}
    for page in result_data.get("pages", []):
        for block in page.get("blocks", []):
            block_id = block.get("id", "")
            if block_id:
                index[block_id] = block
    return index


def crop_url_to_r2_key(crop_url: Optional[str]) -> Optional[str]:
    """Конвертировать legacy crop URL → R2 key.

    Legacy: https://rd1.svarovsky.ru/tree_docs/{project}/{block_id}.pdf
    New: documents/{document_id}/crops/{block_id}.png

    Так как URL-формат может отличаться, извлекаем только path-часть.
    """
    if not crop_url:
        return None

    try:
        parsed = urlparse(crop_url)
        path = parsed.path.lstrip("/")
        # Оставляем path как есть — будет использоваться как legacy_crop_key
        return path if path else None
    except Exception:
        return None


def map_recognition_attempt(
    block_id: str,
    run_id: str,
    legacy_block: dict,
    result_block: Optional[dict],
    source_id: str,
    prompt_template_id: Optional[str],
    geometry_rev: int = 1,
) -> Optional[dict[str, Any]]:
    """Создать синтетический recognition_attempt из legacy данных.

    Args:
        block_id: UUID нового блока
        run_id: UUID recognition_run
        legacy_block: блок из annotation.json
        result_block: блок из result.json (может быть None)
        source_id: UUID OCR source
        prompt_template_id: UUID prompt template
        geometry_rev: текущая ревизия геометрии
    """
    ocr_text = legacy_block.get("ocr_text")

    # Не создаём attempt если нет OCR результата
    if ocr_text is None or not ocr_text.strip():
        return None

    # Определяем статус
    if is_ocr_error(ocr_text):
        attempt_status = "failed"
        error_message = ocr_text.strip()
    else:
        attempt_status = "success"
        error_message = None

    attempt: dict[str, Any] = {
        "id": new_uuid(),
        "run_id": run_id,
        "block_id": block_id,
        "geometry_rev": geometry_rev,
        "source_id": source_id,
        "model_name": "legacy_unknown",
        "prompt_template_id": prompt_template_id or source_id,  # fallback
        "prompt_snapshot_json": json.dumps(
            legacy_block.get("prompt", {"system": "", "user": ""}),
            ensure_ascii=False,
        ),
        "attempt_no": 1,
        "fallback_no": 0,
        "status": attempt_status,
        "selected_as_current": attempt_status == "success",
    }

    # Успешный результат
    if attempt_status == "success":
        attempt["normalized_text"] = ocr_text

    # Ошибка
    if attempt_status == "failed":
        attempt["error_message"] = error_message

    # Обогащение из result.json
    if result_block:
        attempt["render_html"] = result_block.get("ocr_html")
        attempt["structured_json"] = json.dumps(
            result_block.get("ocr_json"), ensure_ascii=False,
        ) if result_block.get("ocr_json") else None

        ocr_meta = result_block.get("ocr_meta")
        if ocr_meta:
            attempt["quality_flags_json"] = json.dumps(ocr_meta, ensure_ascii=False)

            # Извлечь model_name из meta если есть
            methods = ocr_meta.get("method", [])
            if methods:
                attempt["model_name"] = methods[0] if isinstance(methods, list) else str(methods)

    return attempt


def map_block_enrichment(
    result_block: Optional[dict],
) -> dict[str, Any]:
    """Извлечь данные из result.json для обновления blocks row.

    Возвращает dict с полями для UPDATE blocks SET ...
    """
    updates: dict[str, Any] = {}

    if not result_block:
        return updates

    # render_html для блока
    ocr_html = result_block.get("ocr_html")
    if ocr_html:
        updates["current_render_html"] = ocr_html

    # structured_json (для stamp/image блоков)
    ocr_json = result_block.get("ocr_json")
    if ocr_json:
        updates["current_structured_json"] = json.dumps(ocr_json, ensure_ascii=False)

    # crop_url → current_crop_key
    crop_url = result_block.get("crop_url")
    r2_key = crop_url_to_r2_key(crop_url)
    if r2_key:
        updates["current_crop_key"] = r2_key
        updates["crop_upload_state"] = "uploaded"

    return updates
