"""Schemas для workspace endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class WorkspaceResponse(BaseModel):
    """Workspace с ролью текущего пользователя."""

    id: str
    name: str
    slug: str
    settings_json: dict = {}
    my_role: str
    member_count: int = 0
    created_at: datetime


class WorkspaceListResponse(BaseModel):
    """Список workspace-ов пользователя."""

    workspaces: list[WorkspaceResponse]
