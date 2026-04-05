"""Маппинг legacy tree_node + annotation → documents + document_pages.

Источники:
- legacy annotations.data (JSONB) — annotation v2 формат
- legacy tree_nodes — metadata документа
- legacy job_files (file_type='pdf') — r2_key оригинального PDF
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from ..utils import new_uuid, now_utc

logger = logging.getLogger("migrate_legacy.document_mapper")


def map_document(
    node: dict,
    annotation_data: dict,
    workspace_id: str,
    document_profile_id: Optional[str],
    pdf_r2_key: Optional[str] = None,
) -> dict[str, Any]:
    """Создать INSERT dict для таблицы documents.

    Args:
        node: строка из legacy tree_nodes
        annotation_data: parsed annotation.data JSONB
        workspace_id: целевой workspace UUID
        document_profile_id: целевой document_profile UUID
        pdf_r2_key: R2 ключ оригинального PDF (из job_files)
    """
    pages = annotation_data.get("pages", [])
    page_count = len(pages)

    # Определяем статус: если есть хотя бы одна аннотация — ready
    status = "ready" if page_count > 0 else "uploading"

    return {
        "id": new_uuid(),
        "workspace_id": workspace_id,
        "title": node.get("name", "Без названия"),
        "original_r2_key": pdf_r2_key,
        "document_profile_id": document_profile_id,
        "status": status,
        "page_count": page_count,
    }


def map_document_pages(
    document_id: str,
    annotation_data: dict,
) -> list[dict[str, Any]]:
    """Создать INSERT dicts для таблицы document_pages.

    Legacy page_number — 0-based, new — 1-based.
    """
    pages = annotation_data.get("pages", [])
    result = []

    for page in pages:
        legacy_page_number = page.get("page_number", 0)
        new_page_number = legacy_page_number + 1

        result.append({
            "id": new_uuid(),
            "document_id": document_id,
            "page_number": new_page_number,
            "width": page.get("width", 0),
            "height": page.get("height", 0),
            "rotation": 0,
        })

    return result


def find_pdf_r2_key(legacy_db, node_id: str) -> Optional[str]:
    """Найти R2 key оригинального PDF для node_id через legacy job_files.

    Логика: берём последний completed job для node_id, затем его job_file с file_type='pdf'.
    """
    row = legacy_db.execute_one(
        """
        SELECT jf.r2_key
        FROM job_files jf
        JOIN jobs j ON j.id = jf.job_id
        WHERE j.node_id = %s
          AND jf.file_type = 'pdf'
          AND j.status = 'done'
        ORDER BY j.completed_at DESC NULLS LAST
        LIMIT 1
        """,
        (node_id,),
    )
    return row["r2_key"] if row else None


def normalize_annotation_data(raw_data: Any) -> dict:
    """Нормализовать annotation.data: string → dict, проверить format_version."""
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except json.JSONDecodeError:
            logger.error("Не удалось распарсить annotation.data как JSON")
            return {}

    if not isinstance(raw_data, dict):
        logger.error("annotation.data не является dict: %s", type(raw_data))
        return {}

    # Проверка flat format (v0): массив блоков вместо структуры с pages
    if isinstance(raw_data, list):
        logger.warning("Обнаружен flat format v0 — требуется конвертация")
        return {"pages": [], "format_version": 0}

    fmt_version = raw_data.get("format_version", 0)
    if fmt_version < 2:
        logger.info("Annotation format_version=%d — будет мигрирован", fmt_version)

    return raw_data
