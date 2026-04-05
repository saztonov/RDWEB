"""Workspace endpoints — список и детали workspace-ов."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from contracts import WorkspaceListResponse, WorkspaceResponse

from ..auth import CurrentUser, get_current_user, get_supabase
from ..permissions.checks import require_workspace_member

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("/", response_model=WorkspaceListResponse)
def list_workspaces(user: CurrentUser = Depends(get_current_user)) -> WorkspaceListResponse:
    """Список workspace-ов текущего пользователя.

    Global admin видит все workspace-ы.
    """
    sb = get_supabase()

    if user.is_admin:
        # Admin видит все
        result = sb.table("workspaces").select("*").order("created_at").execute()
        workspaces = []
        for row in result.data or []:
            # Посчитать members
            count_result = (
                sb.table("workspace_members")
                .select("id", count="exact")
                .eq("workspace_id", row["id"])
                .execute()
            )
            workspaces.append(
                WorkspaceResponse(
                    id=row["id"],
                    name=row["name"],
                    slug=row["slug"],
                    settings_json=row.get("settings_json") or {},
                    my_role="admin",
                    member_count=count_result.count or 0,
                    created_at=row["created_at"],
                )
            )
    else:
        # Обычный user — только свои workspace-ы
        result = (
            sb.table("workspace_members")
            .select("role, workspaces(*)")
            .eq("user_id", user.id)
            .execute()
        )
        workspaces = []
        for row in result.data or []:
            ws = row.get("workspaces")
            if not isinstance(ws, dict):
                continue
            # Посчитать members
            count_result = (
                sb.table("workspace_members")
                .select("id", count="exact")
                .eq("workspace_id", ws["id"])
                .execute()
            )
            workspaces.append(
                WorkspaceResponse(
                    id=ws["id"],
                    name=ws["name"],
                    slug=ws["slug"],
                    settings_json=ws.get("settings_json") or {},
                    my_role=row["role"],
                    member_count=count_result.count or 0,
                    created_at=ws["created_at"],
                )
            )

    return WorkspaceListResponse(workspaces=workspaces)


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(
    workspace_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> WorkspaceResponse:
    """Детали workspace-а. Проверяет membership."""
    role = require_workspace_member(workspace_id, user)

    sb = get_supabase()
    result = sb.table("workspaces").select("*").eq("id", workspace_id).single().execute()
    ws = result.data

    count_result = (
        sb.table("workspace_members")
        .select("id", count="exact")
        .eq("workspace_id", workspace_id)
        .execute()
    )

    return WorkspaceResponse(
        id=ws["id"],
        name=ws["name"],
        slug=ws["slug"],
        settings_json=ws.get("settings_json") or {},
        my_role=role,
        member_count=count_result.count or 0,
        created_at=ws["created_at"],
    )
