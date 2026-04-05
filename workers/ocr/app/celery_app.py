"""Конфигурация Celery для OCR задач.

Паттерны из legacy_project/services/remote_ocr/server/celery_app.py:
- visibility_timeout=86400 (24h для длинных OCR задач)
- task_acks_late=True (подтверждение после выполнения)
- task_reject_on_worker_lost=False (zombie_detector восстанавливает задачи)
- worker_max_tasks_per_child (защита от memory leaks)
"""

from __future__ import annotations

import logging

from celery import Celery

from .config import get_worker_settings

logger = logging.getLogger(__name__)

settings = get_worker_settings()

celery_app = Celery(
    "ocr_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    # Сериализация
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Worker
    worker_concurrency=settings.celery_concurrency,
    worker_prefetch_multiplier=settings.worker_prefetch,
    worker_max_tasks_per_child=settings.worker_max_tasks_per_child,
    # Broker — 24h visibility для длинных OCR задач
    # Без этого: задачи переотправляются пока ещё выполняются (дубликаты)
    broker_transport_options={"visibility_timeout": 86400},
    # Надёжность задач
    # acks_late: подтверждение только после завершения (защита от потери данных)
    task_acks_late=True,
    # reject_on_worker_lost=False: НЕ перепоставлять при падении worker-а
    # — zombie_detector восстанавливает задачи вручную, избегая бесконечных циклов
    task_reject_on_worker_lost=False,
    # Таймауты
    task_soft_time_limit=settings.task_soft_timeout,
    task_time_limit=settings.task_hard_timeout,
    task_default_retry_delay=settings.task_retry_delay,
    # Результаты
    result_expires=3600,
    # Приоритетная очередь
    task_default_priority=settings.default_task_priority,
    task_queue_max_priority=10,
    # Авто-импорт задач
    imports=["app.tasks", "app.jobs.model_sync", "app.jobs.health_probe"],
    # Beat schedule — периодические задачи
    beat_schedule={
        "sync-source-models": {
            "task": "ocr.sync_source_models",
            "schedule": 300.0,  # каждые 5 минут
        },
        "probe-source-health": {
            "task": "ocr.probe_source_health",
            "schedule": 60.0,  # каждую минуту
        },
    },
)
