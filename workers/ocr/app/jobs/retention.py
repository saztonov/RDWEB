"""Retention policy — автоочистка старых записей из операционных таблиц.

Запускается Celery beat ежедневно.
Удаляет:
- system_events старше 30 дней
- service_health_checks старше 7 дней
- worker_heartbeats с last_seen_at старше 1 дня
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from ..celery_app import celery_app
from ..config import get_worker_settings
from ..infra.db import get_db
from ..infra.event_writer import write_event

logger = logging.getLogger(__name__)

# Retention periods
EVENTS_RETENTION_DAYS = 30
HEALTH_CHECKS_RETENTION_DAYS = 7
HEARTBEATS_RETENTION_DAYS = 1


@celery_app.task(name="ocr.cleanup_retention", ignore_result=True)
def cleanup_retention() -> dict:
    """Очистка устаревших записей из операционных таблиц."""
    settings = get_worker_settings()
    if not settings.supabase_url or not settings.supabase_key:
        return {"status": "skipped", "reason": "no_supabase"}

    sb = get_db()
    now = datetime.now(timezone.utc)
    summary: dict[str, int] = {}

    # system_events старше 30 дней
    events_cutoff = (now - timedelta(days=EVENTS_RETENTION_DAYS)).isoformat()
    try:
        result = (
            sb.table("system_events")
            .delete()
            .lt("created_at", events_cutoff)
            .execute()
        )
        deleted = len(result.data) if result.data else 0
        summary["system_events"] = deleted
    except Exception:
        logger.exception("Ошибка очистки system_events")
        summary["system_events"] = -1

    # service_health_checks старше 7 дней
    health_cutoff = (now - timedelta(days=HEALTH_CHECKS_RETENTION_DAYS)).isoformat()
    try:
        result = (
            sb.table("service_health_checks")
            .delete()
            .lt("checked_at", health_cutoff)
            .execute()
        )
        deleted = len(result.data) if result.data else 0
        summary["service_health_checks"] = deleted
    except Exception:
        logger.exception("Ошибка очистки service_health_checks")
        summary["service_health_checks"] = -1

    # worker_heartbeats с last_seen_at старше 1 дня
    heartbeats_cutoff = (now - timedelta(days=HEARTBEATS_RETENTION_DAYS)).isoformat()
    try:
        result = (
            sb.table("worker_heartbeats")
            .delete()
            .lt("last_seen_at", heartbeats_cutoff)
            .execute()
        )
        deleted = len(result.data) if result.data else 0
        summary["worker_heartbeats"] = deleted
    except Exception:
        logger.exception("Ошибка очистки worker_heartbeats")
        summary["worker_heartbeats"] = -1

    logger.info("Retention cleanup completed: %s", summary)

    # Записать событие об очистке
    write_event(
        event_type="retention_cleanup",
        severity="info",
        source_service="worker",
        payload=summary,
    )

    return summary
