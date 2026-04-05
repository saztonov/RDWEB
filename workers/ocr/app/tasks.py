"""OCR tasks — placeholder для Phase 1.

Импортируем celery_signals чтобы зарегистрировать lifecycle хуки.
"""

from __future__ import annotations

from . import celery_signals as _  # noqa: F401 — регистрация signal handlers
from .celery_app import celery_app


@celery_app.task(name="ocr.health_check")
def health_check() -> dict:
    """Health check task — подтверждает что worker жив и принимает задачи."""
    return {"status": "ok", "worker": "ocr"}
