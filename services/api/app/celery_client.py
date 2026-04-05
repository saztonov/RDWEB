"""Celery client для отправки OCR задач из API.

API не запускает worker — только отправляет задачи через broker.
"""

from __future__ import annotations

import os
from functools import lru_cache

from celery import Celery


@lru_cache
def get_celery_app() -> Celery:
    """Получить Celery app для отправки задач."""
    broker_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    app = Celery("ocr_dispatch", broker=broker_url)
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
    )
    return app
