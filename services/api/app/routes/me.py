"""GET /api/me — текущий пользователь и его workspace-ы."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from contracts import MeResponse, WorkspaceMemberInfo

from ..auth import CurrentUser, get_current_user, get_supabase
from ..permissions.audit import write_system_event

router = APIRouter(tags=["auth"])


@router.get("/me", response_model=MeResponse)
def get_me(user: CurrentUser = Depends(get_current_user)) -> MeResponse:
    """Текущий пользователь + список workspace-ов с ролями."""
    sb = get_supabase()

    # Получить workspace memberships с именами workspace-ов
    result = (
        sb.table("workspace_members")
        .select("workspace_id, role, workspaces(name)")
        .eq("user_id", user.id)
        .execute()
    )

    workspaces = []
    for row in result.data or []:
        ws_data = row.get("workspaces")
        ws_name = ws_data["name"] if isinstance(ws_data, dict) else ""
        workspaces.append(
            WorkspaceMemberInfo(
                workspace_id=row["workspace_id"],
                workspace_name=ws_name,
                role=row["role"],
            )
        )

    # Audit: пользователь обратился к /me
    write_system_event(
        event_type="user_api_access",
        severity="info",
        payload={"user_id": user.id, "endpoint": "/api/me"},
    )

    return MeResponse(
        id=user.id,
        email=user.email,
        is_admin=user.is_admin,
        workspaces=workspaces,
    )
