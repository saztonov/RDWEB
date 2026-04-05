"""FastAPI dependencies для аутентификации и авторизации.

get_current_user — основной dependency: валидирует JWT через Supabase Auth.
require_admin — проверяет глобального админа (is_admin в app_metadata).
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from ..logging_config import get_logger
from .models import CurrentUser
from .supabase_client import get_supabase

_logger = get_logger(__name__)


def _extract_token(authorization: str | None) -> str:
    """Извлечь Bearer token из Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header отсутствует",
        )
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный формат Authorization header. Ожидается: Bearer <token>",
        )
    return parts[1]


def get_current_user(authorization: str | None = Header(None)) -> CurrentUser:
    """Валидировать JWT и вернуть текущего пользователя.

    Использует supabase.auth.get_user(token) — проверяет signature,
    expiration, revocation через Supabase GoTrue.
    """
    token = _extract_token(authorization)
    supabase = get_supabase()

    try:
        response = supabase.auth.get_user(token)
    except Exception as exc:
        _logger.warning("JWT validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидный или просроченный токен",
        ) from exc

    user = response.user
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
        )

    is_admin = bool((user.app_metadata or {}).get("is_admin", False))

    return CurrentUser(
        id=user.id,
        email=user.email or "",
        is_admin=is_admin,
    )


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """get_current_user + проверка глобального админа.

    Использует Depends(get_current_user), чтобы dependency override в тестах
    корректно применялся и для admin checks.
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются права администратора",
        )
    return user
