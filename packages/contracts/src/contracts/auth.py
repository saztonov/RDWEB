"""Schemas для auth endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class UserResponse(BaseModel):
    """Базовая информация о пользователе."""

    id: str
    email: str
    is_admin: bool = False


class WorkspaceMemberInfo(BaseModel):
    """Членство пользователя в workspace."""

    workspace_id: str
    workspace_name: str
    role: str


class MeResponse(UserResponse):
    """Ответ GET /api/me — пользователь + его workspace-ы."""

    workspaces: list[WorkspaceMemberInfo] = []
