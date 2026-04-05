"""Celery lifecycle signals — логирование задач (паттерн из legacy).

Регистрирует хуки на task_prerun, task_postrun, task_failure
для структурированного логирования жизненного цикла задач.
"""

from __future__ import annotations

import logging
import time

import psutil
from celery.signals import task_failure, task_postrun, task_prerun

logger = logging.getLogger("worker.signals")

# Время старта задач для подсчёта duration
_task_start_times: dict[str, float] = {}


def _get_memory_mb() -> float:
    """Текущее потребление памяти процессом в MB."""
    return psutil.Process().memory_info().rss / (1024 * 1024)


@task_prerun.connect
def on_task_prerun(sender=None, task_id=None, task=None, **kwargs):  # type: ignore[no-untyped-def]
    _task_start_times[task_id] = time.monotonic()
    logger.info(
        "Task started: %s [%s] (memory: %.0f MB)",
        sender.name if sender else "unknown",
        task_id,
        _get_memory_mb(),
    )


@task_postrun.connect
def on_task_postrun(sender=None, task_id=None, state=None, **kwargs):  # type: ignore[no-untyped-def]
    duration = 0.0
    if task_id in _task_start_times:
        duration = time.monotonic() - _task_start_times.pop(task_id)
    logger.info(
        "Task finished: %s [%s] state=%s duration=%.1fs (memory: %.0f MB)",
        sender.name if sender else "unknown",
        task_id,
        state,
        duration,
        _get_memory_mb(),
    )


@task_failure.connect
def on_task_failure(sender=None, task_id=None, exception=None, **kwargs):  # type: ignore[no-untyped-def]
    _task_start_times.pop(task_id, None)
    logger.error(
        "Task failed: %s [%s] error=%s (memory: %.0f MB)",
        sender.name if sender else "unknown",
        task_id,
        repr(exception),
        _get_memory_mb(),
    )
