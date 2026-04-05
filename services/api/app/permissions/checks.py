"""Permission checks — проверки membership, admin, document access.

Все запросы через Supabase service_role client (обходит RLS).
Backend сам проверяет permissions в Python — RLS остаётся как safety net.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from ..auth.models import CurrentUser
from ..auth.supabase_client import get_supabase
from ..logging_config import get_logger

_logger = get_logger(__name__)

# Роли с правами администрирования workspace
_ADMIN_ROLES = {"owner", "admin"}


def get_workspace_role(user_id: str, workspace_id: str) -> str | None:
    """Получить роль пользователя в workspace.

    Returns:
        role string (owner/admin/member/viewer) или None если не member.
    """
    sb = get_supabase()
    result = (
        sb.table("workspace_members")
        .select("role")
        .eq("workspace_id", workspace_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if result.data is None:
        return None
    return result.data["role"]


def require_workspace_member(workspace_id: str, user: CurrentUser) -> str:
    """Проверить что пользователь — member workspace.

    Global admin пропускается без проверки membership.

    Returns:
        role string.

    Raises:
        HTTPException 404 если workspace не найден или нет доступа.
    """
    if user.is_admin:
        return "admin"

    role = get_workspace_role(user.id, workspace_id)
    if role is None:
        # 404, а не 403 — не раскрываем existence
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace не найден",
        )
    return role


def require_workspace_admin(workspace_id: str, user: CurrentUser) -> None:
    """Проверить что пользователь — admin/owner workspace.

    Global admin пропускается.

    Raises:
        HTTPException 403/404.
    """
    if user.is_admin:
        return

    role = get_workspace_role(user.id, workspace_id)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace не найден",
        )
    if role not in _ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются права admin или owner workspace",
        )


def get_document_workspace_id(document_id: str) -> str | None:
    """Получить workspace_id документа."""
    sb = get_supabase()
    result = (
        sb.table("documents")
        .select("workspace_id")
        .eq("id", document_id)
        .maybe_single()
        .execute()
    )
    if result.data is None:
        return None
    return result.data["workspace_id"]


def require_document_access(document_id: str, user: CurrentUser) -> str:
    """Проверить доступ к документу через workspace membership.

    Global admin пропускается.

    Returns:
        role string.

    Raises:
        HTTPException 404 если документ не найден или нет доступа.
    """
    if user.is_admin:
        # Проверяем что документ существует
        ws_id = get_document_workspace_id(document_id)
        if ws_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Документ не найден",
            )
        return "admin"

    ws_id = get_document_workspace_id(document_id)
    if ws_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Документ не найден",
        )

    role = get_workspace_role(user.id, ws_id)
    if role is None:
        # 404, а не 403 — не раскрываем existence
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Документ не найден",
        )
    return role
