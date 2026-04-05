"""Upload финального crop блока в R2.

R2 key format: documents/{document_id}/crops/{block_id}.png
Обновляет blocks.crop_upload_state и blocks.current_crop_key.
OCR результат в Postgres НЕ зависит от успешности upload.
"""

from __future__ import annotations

import logging
from pathlib import Path

import boto3

from ..config import get_worker_settings
from .db import get_db

logger = logging.getLogger(__name__)


def _get_r2_client():
    """Создать boto3 client для Cloudflare R2."""
    settings = get_worker_settings()
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def build_crop_r2_key(document_id: str, block_id: str) -> str:
    """R2 key для crop файла блока."""
    return f"documents/{document_id}/crops/{block_id}.png"


def upload_crop(
    block_id: str,
    document_id: str,
    local_path: Path,
) -> str:
    """Upload crop PNG в R2 и обновить блок в БД.

    Returns:
        R2 key загруженного файла.

    Raises:
        Exception при ошибке upload.
    """
    settings = get_worker_settings()
    r2_key = build_crop_r2_key(document_id, block_id)

    client = _get_r2_client()
    client.upload_file(
        str(local_path),
        settings.r2_bucket_name,
        r2_key,
        ExtraArgs={"ContentType": "image/png"},
    )

    # Обновить статус в БД
    db = get_db()
    db.table("blocks").update({
        "crop_upload_state": "uploaded",
        "current_crop_key": r2_key,
    }).eq("id", block_id).execute()

    logger.info("Crop uploaded: block=%s, key=%s", block_id, r2_key)
    return r2_key


def mark_upload_failed(block_id: str) -> None:
    """Отметить неудачный upload crop — block status НЕ меняется."""
    try:
        db = get_db()
        db.table("blocks").update({
            "crop_upload_state": "failed",
        }).eq("id", block_id).execute()
        logger.warning("Crop upload marked failed: block=%s", block_id)
    except Exception as exc:
        logger.error("Failed to mark crop_upload_state=failed: block=%s, error=%s", block_id, exc)
