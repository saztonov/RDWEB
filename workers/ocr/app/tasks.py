"""OCR tasks — runtime pipeline задачи + background jobs.

Импортируем celery_signals чтобы зарегистрировать lifecycle хуки.
Импортируем jobs чтобы зарегистрировать beat tasks.
"""

from __future__ import annotations

import logging
from pathlib import Path

from celery.exceptions import SoftTimeLimitExceeded

from . import celery_signals as _  # noqa: F401 — регистрация signal handlers
from .celery_app import celery_app
from .config import get_worker_settings
from .jobs import health_probe as _hp  # noqa: F401 — регистрация beat task
from .jobs import model_sync as _ms  # noqa: F401 — регистрация beat task

logger = logging.getLogger(__name__)


@celery_app.task(name="ocr.health_check")
def health_check() -> dict:
    """Health check task — подтверждает что worker жив и принимает задачи."""
    return {"status": "ok", "worker": "ocr"}


@celery_app.task(
    name="ocr.process_page_blocks",
    bind=True,
    acks_late=True,
    max_retries=0,
    soft_time_limit=3600,
    time_limit=4200,
)
def process_page_blocks_task(
    self,
    run_id: str,
    document_id: str,
    page_number: int,
    block_ids: list[str],
) -> dict:
    """Обработка всех блоков одной страницы документа.

    Основная задача OCR pipeline:
    1. Acquire execution lock
    2. Ensure PDF cached locally
    3. Render page, crop каждый блок, OCR, verify, write
    4. Dispatch crop upload tasks
    5. Release lock, update run status
    """
    from .infra.db import get_db
    from .infra.execution_lock import acquire_lock, release_lock
    from .infra.r2_uploader import build_crop_r2_key
    from .pipeline.page_processor import PageProcessor

    from ocr_core import PdfCacheManager

    settings = get_worker_settings()
    task_id = self.request.id or "unknown"

    logger.info(
        "process_page_blocks started: run=%s, doc=%s, page=%d, blocks=%d",
        run_id, document_id, page_number, len(block_ids),
    )

    # 1. Execution lock
    if not acquire_lock(run_id, page_number, task_id):
        logger.warning("Lock already held, aborting: run=%s, page=%d", run_id, page_number)
        return {"status": "skipped", "reason": "lock_held"}

    try:
        db = get_db()

        # Обновить run status → running (если ещё pending)
        db.table("recognition_runs").update({
            "status": "running",
            "started_at": "now()",
        }).eq("id", run_id).eq("status", "pending").execute()

        # 2. Ensure PDF cached
        cache = PdfCacheManager(Path(settings.pdf_cache_dir), settings.pdf_cache_ttl)

        doc_result = (
            db.table("documents")
            .select("original_r2_key")
            .eq("id", document_id)
            .single()
            .execute()
        )
        r2_key = doc_result.data["original_r2_key"]

        def download_pdf(local_path: str) -> None:
            import boto3
            client = boto3.client(
                "s3",
                endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=settings.r2_access_key_id,
                aws_secret_access_key=settings.r2_secret_access_key,
                region_name="auto",
            )
            client.download_file(settings.r2_bucket_name, r2_key, local_path)

        pdf_path = cache.ensure_cached(document_id, download_pdf)

        # 3. Process page
        processor = PageProcessor(
            run_id=run_id,
            document_id=document_id,
            page_number=page_number,
            block_ids=block_ids,
            pdf_path=pdf_path,
            db=db,
        )

        page_result = processor.process()

        # 4. Dispatch crop upload tasks
        for br in page_result.block_results:
            if br.skipped or not br.crop_local_path:
                continue
            if br.crop_local_path.exists():
                r2_crop_key = build_crop_r2_key(document_id, br.block_id)
                upload_crop_task.apply_async(
                    args=[br.block_id, document_id, str(br.crop_local_path), r2_crop_key],
                    priority=3,  # Ниже приоритет чем OCR tasks
                )

        # 5. Проверить: все ли page tasks для этого run завершен��?
        _check_run_completion(run_id, db)

        logger.info(
            "process_page_blocks done: run=%s, page=%d, recognized=%d, failed=%d, review=%d, skipped=%d",
            run_id, page_number,
            page_result.recognized, page_result.failed,
            page_result.manual_review, page_result.skipped,
        )

        return {
            "status": "completed",
            "page_number": page_number,
            "recognized": page_result.recognized,
            "failed": page_result.failed,
            "manual_review": page_result.manual_review,
            "skipped": page_result.skipped,
        }

    except SoftTimeLimitExceeded:
        logger.error("Soft timeout: run=%s, page=%d", run_id, page_number)
        # Пометить необработанные блоки как failed
        db = get_db()
        for block_id in block_ids:
            try:
                block = db.table("blocks").select("current_status").eq("id", block_id).maybe_single().execute()
                if block.data and block.data["current_status"] == "processing":
                    db.table("blocks").update({"current_status": "failed"}).eq("id", block_id).execute()
            except Exception:
                pass
        return {"status": "timeout", "page_number": page_number}

    except Exception as exc:
        logger.error(
            "process_page_blocks failed: run=%s, page=%d: %s",
            run_id, page_number, exc, exc_info=True,
        )
        return {"status": "error", "page_number": page_number, "error": str(exc)}

    finally:
        release_lock(run_id, page_number, task_id)


@celery_app.task(
    name="ocr.upload_crop",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def upload_crop_task(
    self,
    block_id: str,
    document_id: str,
    crop_local_path: str,
    r2_key: str,
) -> dict:
    """Upload финального crop в R2. Retryable.

    OCR результат в Postgres НЕ зависит от успешности upload.
    При исчер��ании retries — crop_upload_state="failed", block status не меняется.
    """
    from .infra.r2_uploader import mark_upload_failed, upload_crop

    path = Path(crop_local_path)
    if not path.exists():
        logger.warning("Crop file not found: %s (block=%s)", crop_local_path, block_id)
        mark_upload_failed(block_id)
        return {"status": "failed", "reason": "file_not_found"}

    try:
        upload_crop(block_id, document_id, path)
        return {"status": "uploaded", "r2_key": r2_key}
    except Exception as exc:
        logger.warning(
            "Crop upload failed (attempt %d/%d): block=%s, error=%s",
            self.request.retries + 1, self.max_retries + 1,
            block_id, exc,
        )
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        else:
            mark_upload_failed(block_id)
            return {"status": "failed", "error": str(exc)}


def _check_run_completion(run_id: str, db) -> None:
    """Проверить завершён ��и run (все бло��и обработаны)."""
    result = (
        db.table("recognition_runs")
        .select("total_blocks, processed_blocks")
        .eq("id", run_id)
        .single()
        .execute()
    )
    run = result.data
    if run["processed_blocks"] >= run["total_blocks"]:
        from datetime import datetime, timezone
        db.table("recognition_runs").update({
            "status": "completed",
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", run_id).execute()
        logger.info("Recognition run completed: %s", run_id)
