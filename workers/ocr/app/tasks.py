"""OCR tasks — базовые задачи + импорт background jobs.

Импортируем celery_signals чтобы зарегистрировать lifecycle хуки.
Импортируем jobs чтобы зарегистрировать beat tasks.
"""

from __future__ import annotations

from . import celery_signals as _  # noqa: F401 — регистрация signal handlers
from .celery_app import celery_app
from .jobs import health_probe as _hp  # noqa: F401 — регистрация beat task
from .jobs import model_sync as _ms  # noqa: F401 — регистрация beat task


@celery_app.task(name="ocr.health_check")
def health_check() -> dict:
    """Health check task — подтверждает что worker жив и принимает задачи."""
    return {"status": "ok", "worker": "ocr"}
