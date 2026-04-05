"""Execution lock — защита от дублирования page task через Redis SET NX.

Адаптация из legacy execution_lock.py.
Key: ocr:page:{run_id}:{page_number}, value: celery_task_id.
TTL: hard_timeout + 300s (защита от stale lock при крэше).
"""

from __future__ import annotations

import logging

import redis

from ..config import get_worker_settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "ocr:page"


def _get_redis() -> redis.Redis:
    """Получить Redis клиент из broker URL."""
    settings = get_worker_settings()
    return redis.Redis.from_url(settings.celery_broker_url)


def _lock_key(run_id: str, page_number: int) -> str:
    return f"{_KEY_PREFIX}:{run_id}:{page_number}"


def acquire_lock(
    run_id: str,
    page_number: int,
    task_id: str,
) -> bool:
    """Попытка захватить lock. True = успешно, False = уже занят.

    Fail-closed: при ошибке Redis возвращает False.
    """
    settings = get_worker_settings()
    ttl = settings.task_hard_timeout + 300

    try:
        r = _get_redis()
        key = _lock_key(run_id, page_number)
        acquired = r.set(key, task_id, nx=True, ex=ttl)

        if acquired:
            logger.info("Lock acquired: %s (task=%s)", key, task_id)
        else:
            holder = r.get(key)
            holder_str = holder.decode() if holder else "unknown"
            logger.warning("Lock already held: %s (holder=%s, requester=%s)", key, holder_str, task_id)

        return bool(acquired)
    except Exception as exc:
        logger.error("Redis lock error: %s", exc)
        return False


def release_lock(
    run_id: str,
    page_number: int,
    task_id: str,
) -> None:
    """Освободить lock только если owner = task_id."""
    try:
        r = _get_redis()
        key = _lock_key(run_id, page_number)
        current = r.get(key)
        if current and current.decode() == task_id:
            r.delete(key)
            logger.info("Lock released: %s (task=%s)", key, task_id)
        elif current:
            logger.warning(
                "Lock release skipped (not owner): %s (holder=%s, requester=%s)",
                key, current.decode(), task_id,
            )
    except Exception as exc:
        logger.error("Redis unlock error: %s", exc)
