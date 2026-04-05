"""Audit helpers — запись system_events, block_events, audit metadata.

Fire-and-forget: ошибки записи логируются, но не блокируют основной flow.
"""

from __future__ import annotations

from typing import Any

from ..auth.models import CurrentUser
from ..auth.supabase_client import get_supabase
from ..logging_config import get_logger

_logger = get_logger(__name__)


def write_system_event(
    event_type: str,
    severity: str = "info",
    source_service: str = "backend",
    payload: dict[str, Any] | None = None,
) -> None:
    """Записать событие в system_events.

    Fire-and-forget: исключения логируются как warning.
    """
    try:
        sb = get_supabase()
        sb.table("system_events").insert({
            "event_type": event_type,
            "severity": severity,
            "source_service": source_service,
            "payload_json": payload or {},
        }).execute()
    except Exception:
        _logger.warning("Не удалось записать system_event: %s", event_type, exc_info=True)


def write_block_event(
    block_id: str,
    event_type: str,
    actor_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Записать событие в block_events.

    Fire-and-forget: исключения логируются как warning.
    """
    try:
        sb = get_supabase()
        sb.table("block_events").insert({
            "block_id": block_id,
            "event_type": event_type,
            "actor_id": actor_id,
            "payload_json": payload or {},
        }).execute()
    except Exception:
        _logger.warning("Не удалось записать block_event: %s/%s", block_id, event_type, exc_info=True)


def stamp_created(data: dict[str, Any], user: CurrentUser) -> dict[str, Any]:
    """Добавить created_by и updated_by к данным для INSERT."""
    return {**data, "created_by": user.id, "updated_by": user.id}


def stamp_updated(data: dict[str, Any], user: CurrentUser) -> dict[str, Any]:
    """Добавить updated_by к данным для UPDATE."""
    return {**data, "updated_by": user.id}
