"""Бизнес-логика генерации export документов.

Export строится ТОЛЬКО из current state блоков в БД (правило #5, #16 пролога).
Файл не хранится в R2 — генерируется на лету, в document_exports только metadata/history.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException

from ..auth.supabase_client import get_supabase
from .export.generator_common import (
    INHERITABLE_STAMP_FIELDS,
    collect_inherited_stamp,
    find_page_stamp_from_dicts,
)
from .export.html_generator import generate_html
from .export.md_generator import generate_markdown
from .r2_client import R2Client

logger = logging.getLogger(__name__)

# Presigned URL TTL для crop links — 24 часа
_CROP_URL_TTL = 86400


# ── Сортировка блоков ────────────────────────────────────────────────


def _sort_key(block: dict) -> tuple:
    """Ключ сортировки: page_number -> reading_order -> Y (top->bottom) -> X (left->right)."""
    bbox = block.get("bbox_json") or {}
    reading_order = block.get("reading_order")
    return (
        block.get("page_number", 0),
        reading_order if reading_order is not None else 999_999,
        bbox.get("y", 0.0),
        bbox.get("x", 0.0),
    )


# ── Stamp propagation ───────────────────────────────────────────────


def _collect_stamp_data(
    sorted_blocks: List[Dict],
) -> Tuple[Optional[Dict], Dict[int, Optional[Dict]]]:
    """Собрать stamp данные для экспорта.

    Returns:
        (inherited_stamp, page_stamps) — общие inherited поля и stamp по каждой странице.
    """
    # Inherited stamp (мода по всем stamp блокам)
    inherited_stamp = collect_inherited_stamp(sorted_blocks)

    # Page stamps: группируем блоки по page_number, ищем stamp на каждой странице
    page_stamps: Dict[int, Optional[Dict]] = {}
    blocks_by_page: Dict[int, List[Dict]] = {}
    for block in sorted_blocks:
        pn = block.get("page_number", 0)
        blocks_by_page.setdefault(pn, []).append(block)

    for pn, page_blocks in blocks_by_page.items():
        page_stamps[pn] = find_page_stamp_from_dicts(page_blocks)

    return inherited_stamp, page_stamps


# ── Crop URL map ─────────────────────────────────────────────────────


def _build_crop_url_map(
    blocks: List[Dict], r2_client: Optional[R2Client]
) -> Dict[str, str]:
    """Сгенерировать presigned GET URL для каждого блока с crop."""
    if not r2_client:
        return {}

    crop_urls: Dict[str, str] = {}
    for block in blocks:
        crop_key = block.get("current_crop_key")
        if crop_key:
            try:
                url = r2_client.generate_presigned_get_url(
                    key=crop_key, expires_in=_CROP_URL_TTL
                )
                crop_urls[block["id"]] = url
            except Exception:
                logger.warning(
                    "Не удалось сгенерировать presigned URL для crop %s",
                    crop_key,
                    exc_info=True,
                )
    return crop_urls


# ── Основные функции ─────────────────────────────────────────────────


def create_export(
    document_id: str,
    output_format: str,
    include_crop_links: bool,
    include_stamp_info: bool,
    r2_client: Optional[R2Client],
) -> Tuple[bytes, str, str, dict]:
    """Создать export документа — генерация файла + запись в document_exports.

    Args:
        document_id: UUID документа
        output_format: "html" или "markdown"
        include_crop_links: вставлять ли ссылки на crop
        include_stamp_info: прокидывать ли stamp info
        r2_client: клиент R2 для presigned URL (может быть None)

    Returns:
        (content_bytes, file_name, content_type, export_record)

    Raises:
        HTTPException: если документ не найден или генерация провалилась
    """
    sb = get_supabase()

    # Получить document title
    doc_resp = (
        sb.table("documents")
        .select("id, title")
        .eq("id", document_id)
        .maybe_single()
        .execute()
    )
    if not doc_resp.data:
        raise HTTPException(status_code=404, detail="Документ не найден")

    doc_title = doc_resp.data.get("title") or "OCR Export"

    # Создать запись в document_exports (status=generating)
    options_json = {
        "output_format": output_format,
        "include_crop_links": include_crop_links,
        "include_stamp_info": include_stamp_info,
    }
    export_insert = (
        sb.table("document_exports")
        .insert({
            "document_id": document_id,
            "export_format": output_format,
            "options_json": options_json,
            "status": "generating",
        })
        .execute()
    )
    export_id = export_insert.data[0]["id"]

    try:
        # Загрузить все не-удалённые блоки документа
        blocks_resp = (
            sb.table("blocks")
            .select("*")
            .eq("document_id", document_id)
            .is_("deleted_at", "null")
            .execute()
        )
        sorted_blocks = sorted(blocks_resp.data or [], key=_sort_key)

        # Stamp propagation
        inherited_stamp: Optional[Dict] = None
        page_stamps: Dict[int, Optional[Dict]] = {}
        if include_stamp_info:
            inherited_stamp, page_stamps = _collect_stamp_data(sorted_blocks)

        # Crop URLs
        crop_urls: Dict[str, str] = {}
        if include_crop_links:
            crop_urls = _build_crop_url_map(sorted_blocks, r2_client)

        # Опции для генератора
        gen_options = {
            "include_crop_links": include_crop_links,
            "include_stamp_info": include_stamp_info,
        }

        # Генерация
        if output_format == "html":
            content_str = generate_html(
                sorted_blocks,
                doc_title,
                inherited_stamp,
                page_stamps,
                crop_urls,
                gen_options,
            )
            ext = "html"
            content_type = "text/html; charset=utf-8"
        else:
            content_str = generate_markdown(
                sorted_blocks,
                doc_title,
                inherited_stamp,
                page_stamps,
                crop_urls,
                gen_options,
            )
            ext = "md"
            content_type = "text/markdown; charset=utf-8"

        content_bytes = content_str.encode("utf-8")

        # Формируем имя файла (безопасное)
        safe_title = "".join(
            c if c.isalnum() or c in " _-" else "_" for c in doc_title
        ).strip()[:80]
        file_name = f"{safe_title}_export.{ext}"

        # Обновить export запись: completed
        now = datetime.now(timezone.utc).isoformat()
        sb.table("document_exports").update({
            "status": "completed",
            "file_name": file_name,
            "file_size": len(content_bytes),
            "completed_at": now,
        }).eq("id", export_id).execute()

        export_record = {
            "id": export_id,
            "document_id": document_id,
            "export_format": output_format,
            "options_json": options_json,
            "file_name": file_name,
            "file_size": len(content_bytes),
            "status": "completed",
            "completed_at": now,
        }

        logger.info(
            "Export создан: document=%s, format=%s, size=%d",
            document_id,
            output_format,
            len(content_bytes),
        )
        return content_bytes, file_name, content_type, export_record

    except HTTPException:
        raise
    except Exception as e:
        # Обновить export запись: failed
        sb.table("document_exports").update({
            "status": "failed",
            "error_message": str(e)[:500],
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", export_id).execute()

        logger.error(
            "Ошибка генерации export: document=%s, error=%s",
            document_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка генерации export: {e}",
        )


def list_exports(document_id: str) -> list[dict]:
    """Получить историю экспортов документа (отсортировано по created_at desc)."""
    sb = get_supabase()
    resp = (
        sb.table("document_exports")
        .select("*")
        .eq("document_id", document_id)
        .order("created_at", desc=True)
        .execute()
    )
    return resp.data or []


def get_export(document_id: str, export_id: str) -> Optional[dict]:
    """Получить metadata одного экспорта."""
    sb = get_supabase()
    resp = (
        sb.table("document_exports")
        .select("*")
        .eq("id", export_id)
        .eq("document_id", document_id)
        .maybe_single()
        .execute()
    )
    return resp.data
