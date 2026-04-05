"""Worker heartbeat — периодическая отправка состояния worker-а.

UPSERT в worker_heartbeats + Redis pub/sub уведомление.
Запускается Celery beat каждые 30 секунд.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import socket
from datetime import datetime, timezone

import redis

from ..celery_app import celery_app
from ..config import get_worker_settings
from ..infra.db import get_db

logger = logging.getLogger(__name__)


def _get_memory_mb() -> float:
    """Получить RSS памяти текущего процесса в мегабайтах."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return round(process.memory_info().rss / (1024 * 1024), 1)
    except ImportError:
        # psutil не установлен — пытаемся через /proc (Linux)
        try:
            with open(f"/proc/{os.getpid()}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return round(int(line.split()[1]) / 1024, 1)
        except Exception:
            pass
    return 0.0


def _get_worker_name() -> str:
    """Уникальное имя worker-а: hostname-pid."""
    hostname = socket.gethostname()
    return f"{hostname}-{os.getpid()}"


@celery_app.task(name="ocr.worker_heartbeat", ignore_result=True)
def worker_heartbeat() -> dict:
    """Отправить heartbeat worker-а."""
    settings = get_worker_settings()
    if not settings.supabase_url or not settings.supabase_key:
        return {"status": "skipped", "reason": "no_supabase"}

    sb = get_db()
    now = datetime.now(timezone.utc).isoformat()

    worker_name = _get_worker_name()
    hostname = socket.gethostname()
    pid = os.getpid()
    memory_mb = _get_memory_mb()

    # Получить количество активных задач через Celery inspect
    active_tasks = 0
    try:
        inspector = celery_app.control.inspect(timeout=5)
        active = inspector.active()
        if active:
            for worker_tasks in active.values():
                active_tasks += len(worker_tasks)
    except Exception:
        logger.debug("Не удалось получить active tasks через inspect")

    heartbeat_data = {
        "worker_name": worker_name,
        "queue_name": "celery",
        "host": hostname,
        "pid": pid,
        "memory_mb": memory_mb,
        "active_tasks": active_tasks,
        "last_seen_at": now,
    }

    # UPSERT: insert or update by worker_name
    try:
        sb.table("worker_heartbeats").upsert(
            heartbeat_data,
            on_conflict="worker_name",
        ).execute()
    except Exception:
        logger.exception("Не удалось записать worker heartbeat")
        return {"status": "error"}

    # Pub/sub уведомление для SSE
    try:
        r = redis.from_url(settings.celery_broker_url, decode_responses=True)
        r.publish("admin:workers", json.dumps(heartbeat_data, default=str))
    except Exception:
        pass

    return {"worker": worker_name, "memory_mb": memory_mb, "active_tasks": active_tasks}
