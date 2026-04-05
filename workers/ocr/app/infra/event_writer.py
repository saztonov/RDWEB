"""Structured event writer — worker-side версия.

Запись в system_events + Redis pub/sub уведомления из контекста Celery worker.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis

from ..config import get_worker_settings
from .db import get_db

logger = logging.getLogger(__name__)

_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    """Lazy-init Redis client для pub/sub."""
    global _redis_client
    if _redis_client is None:
        settings = get_worker_settings()
        _redis_client = redis.from_url(settings.celery_broker_url, decode_responses=True)
    return _redis_client


def write_event(
    event_type: str,
    severity: str,
    source_service: str,
    payload: dict[str, Any] | None = None,
) -> str | None:
    """Записать событие в system_events и опубликовать в Redis pub/sub.

    Returns:
        ID созданной записи или None при ошибке.
    """
    sb = get_db()
    now = datetime.now(timezone.utc).isoformat()

    row = {
        "event_type": event_type,
        "severity": severity,
        "source_service": source_service,
        "payload_json": payload or {},
        "created_at": now,
    }

    try:
        result = sb.table("system_events").insert(row).execute()
        event_id = result.data[0]["id"] if result.data else None
    except Exception:
        logger.exception("Не удалось записать system_event: %s", event_type)
        return None

    # Публикация в Redis pub/sub для SSE
    try:
        message = {
            "id": event_id,
            "event_type": event_type,
            "severity": severity,
            "source_service": source_service,
            "payload_json": payload or {},
            "created_at": now,
        }
        _get_redis().publish("admin:events", json.dumps(message, default=str))
    except Exception:
        logger.warning("Не удалось опубликовать event в Redis pub/sub", exc_info=True)

    return event_id
