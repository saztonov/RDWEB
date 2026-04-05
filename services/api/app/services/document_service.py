"""Бизнес-логика ingestion документов: upload, finalize, metadata extraction.

Правила пролога:
- R2 хранит только original PDF (#6)
- Source of truth — Postgres (#5)
- Секреты тольк�� на backend (#13)
- Overwrite original PDF запрещён для MVP
"""

from __future__ import annotations

import logging

import fitz
from botocore.exceptions import ClientError
from fastapi import HTTPException
from ocr_core import PdfCacheManager

from ..auth.supabase_client import get_supabase
from .r2_client import R2Client

logger = logging.getLogger(__name__)

# R2 key convention: documents/{document_id}/source/original.pdf
_R2_KEY_TEMPLATE = "documents/{document_id}/source/original.pdf"

# Presigned URL TTL
_UPLOAD_URL_TTL = 3600
_DOWNLOAD_URL_TTL = 3600


def _build_r2_key(document_id: str) -> str:
    return _R2_KEY_TEMPLATE.format(document_id=document_id)


def extract_page_metadata(pdf_path: str) -> list[dict]:
    """Открыть PDF через PyMuPDF и из��лечь метаданн��е каждой страницы.

    Returns:
        Список словарей: {page_number, width, height, rotation}.
        page_number: 1-based.
        width/height: PDF points (1/72 inch), округлены до int.
        rotation: градусы (0, 90, 180, 270).
    """
    doc = fitz.open(pdf_path)
    try:
        pages = []
        for i in range(len(doc)):
            page = doc[i]
            pages.append({
                "page_number": i + 1,
                "width": round(page.rect.width),
                "height": round(page.rect.height),
                "rotation": page.rotation,
            })
        return pages
    finally:
        doc.close()


def create_upload(
    workspace_id: str,
    title: str,
    r2: R2Client,
    *,
    created_by: str | None = None,
) -> dict:
    """Создать документ и вернуть presigned PUT URL.

    Returns:
        {document_id, upload_url, r2_key}
    """
    sb = get_supabase()

    insert_data: dict = {
        "workspace_id": workspace_id,
        "title": title,
        "status": "uploading",
    }
    if created_by:
        insert_data["created_by"] = created_by

    result = sb.table("documents").insert(insert_data).execute()
    doc = result.data[0]
    document_id = doc["id"]
    r2_key = _build_r2_key(document_id)

    # Сохранить r2_key
    sb.table("documents").update({"original_r2_key": r2_key}).eq("id", document_id).execute()

    upload_url = r2.generate_presigned_put_url(
        key=r2_key,
        content_type="application/pdf",
        expires_in=_UPLOAD_URL_TTL,
    )

    logger.info("Создан документ %s, r2_key=%s", document_id, r2_key)
    return {
        "document_id": document_id,
        "upload_url": upload_url,
        "r2_key": r2_key,
    }


def finalize(
    document_id: str,
    r2: R2Client,
    pdf_cache: PdfCacheManager,
) -> dict:
    """Финализировать загрузку: проверить PDF в R2, извлечь метаданные страниц.

    Returns:
        {document_id, status, page_count}
    """
    sb = get_supabase()

    result = sb.table("documents").select("*").eq("id", document_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Документ не найден")

    doc = result.data[0]

    # Overwrite запрещён — finalize только для uploading
    if doc["status"] != "uploading":
        raise HTTPException(
            status_code=409,
            detail=f"Документ уже финализирован или в статусе '{doc['status']}'. "
                   "Для MVP перезагрузка original PDF запрещена — создайте новый документ.",
        )

    r2_key = doc.get("original_r2_key") or _build_r2_key(document_id)

    # Проверить что PDF реально загружен в R2
    try:
        head = r2.head_object(r2_key)
        etag = head.get("ETag", "").strip('"')
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code in ("404", "NoSuchKey"):
            raise HTTPException(status_code=400, detail="PDF не найден в R2. Загрузите файл и повторите.")
        raise

    # Скачать в локальный кеш
    local_path = pdf_cache.ensure_cached(
        document_id=document_id,
        download_fn=lambda path: r2.download_file(r2_key, path),
        etag=etag or None,
    )

    # Извлечь метаданные страниц
    try:
        pages = extract_page_metadata(str(local_path))
    except Exception as exc:
        logger.error("Ошибка парсинга PDF %s: %s", document_id, exc)
        sb.table("documents").update({"status": "error"}).eq("id", document_id).execute()
        raise HTTPException(status_code=422, detail=f"Не��алидный PDF файл: {exc}")

    if not pages:
        sb.table("documents").update({"status": "error"}).eq("id", document_id).execute()
        raise HTTPException(status_code=422, detail="PDF не содержит страниц")

    page_count = len(pages)

    # Записать страницы в document_pages
    rows = [
        {
            "document_id": document_id,
            "page_number": p["page_number"],
            "width": p["width"],
            "height": p["height"],
            "rotation": p["rotation"],
        }
        for p in pages
    ]
    sb.table("document_pages").insert(rows).execute()

    # Обновить документ
    sb.table("documents").update({
        "status": "ready",
        "page_count": page_count,
    }).eq("id", document_id).execute()

    logger.info("Документ %s финализирован: %d страниц", document_id, page_count)
    return {
        "document_id": document_id,
        "status": "ready",
        "page_count": page_count,
    }


def get_download_url(document_id: str, r2: R2Client) -> dict:
    """Получить presigned GET URL для скачивания оригинального PDF."""
    sb = get_supabase()

    result = sb.table("documents").select("id, original_r2_key").eq("id", document_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Доку��ент не найден")

    doc = result.data[0]
    r2_key = doc.get("original_r2_key")
    if not r2_key:
        raise HTTPException(status_code=400, detail="У документа нет загруженного PDF")

    download_url = r2.generate_presigned_get_url(
        key=r2_key,
        expires_in=_DOWNLOAD_URL_TTL,
    )
    return {
        "download_url": download_url,
        "expires_in": _DOWNLOAD_URL_TTL,
    }
