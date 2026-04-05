"""SSE endpoint для admin panel — live updates через Redis pub/sub.

Каналы:
- admin:health — обновления health checks
- admin:events — новые system events
- admin:runs — прогресс recognition runs
- admin:workers — heartbeat worker-ов

Аутентификация: EventSource API не поддерживает Authorization header,
поэтому token передаётся через query parameter.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Query, status
from starlette.responses import StreamingResponse

from ..auth.models import CurrentUser
from ..auth.supabase_client import get_supabase
from ..config import get_settings

router = APIRouter(prefix="/admin", tags=["admin-sse"])
logger = logging.getLogger(__name__)

# Каналы Redis pub/sub для SSE
SSE_CHANNELS = ["admin:health", "admin:events", "admin:runs", "admin:workers"]


def _authenticate_sse(token: str | None) -> CurrentUser:
    """Аутентификация для SSE через query param token.

    EventSource API не поддерживает заголовки — используем ?token=.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token отсутствует",
        )

    supabase = get_supabase()
    try:
        response = supabase.auth.get_user(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный или просроченный токен",
        )

    user = response.user
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
        )

    is_admin = bool((user.app_metadata or {}).get("is_admin", False))
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются права администратора",
        )

    return CurrentUser(id=user.id, email=user.email or "", is_admin=True)


async def _sse_generator(redis_url: str):
    """Async generator: подписка на Redis pub/sub, yield SSE frames."""
    import redis.asyncio as aioredis

    r = aioredis.from_url(redis_url, decode_responses=True)
    pubsub = r.pubsub()

    try:
        await pubsub.subscribe(*SSE_CHANNELS)

        # Начальный heartbeat для подтверждения соединения
        yield ": connected\n\n"

        while True:
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                # SSE keep-alive каждые 30 секунд
                yield ": keepalive\n\n"
                continue

            if message is None:
                await asyncio.sleep(0.1)
                continue

            channel = message.get("channel", "")
            data = message.get("data", "")

            if not data or not isinstance(data, str):
                continue

            # Маппинг channel → event type
            event_type = channel.replace("admin:", "")
            yield f"event: {event_type}\ndata: {data}\n\n"

    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("SSE stream error")
    finally:
        await pubsub.unsubscribe(*SSE_CHANNELS)
        await pubsub.close()
        await r.close()


@router.get("/sse")
async def admin_sse(token: str | None = Query(None)):
    """Server-Sent Events для admin dashboard. Только для admin.

    Auth через query param ?token= (EventSource не поддерживает заголовки).
    """
    _authenticate_sse(token)

    settings = get_settings()

    return StreamingResponse(
        _sse_generator(settings.redis_url),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
