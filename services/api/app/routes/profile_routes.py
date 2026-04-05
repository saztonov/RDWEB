"""Profile routes endpoints — список и обновление default prompt template."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from contracts import (
    ProfileRouteListResponse,
    ProfileRoutePatchRequest,
    ProfileRouteResponse,
)

from ..auth import CurrentUser, get_supabase
from ..auth.dependencies import require_admin

router = APIRouter(prefix="/profile-routes", tags=["profile-routes"])


@router.get("/", response_model=ProfileRouteListResponse)
def list_profile_routes(
    user: CurrentUser = Depends(require_admin),
) -> ProfileRouteListResponse:
    """Список всех profile routes с названием профиля."""
    sb = get_supabase()

    result = (
        sb.table("profile_routes")
        .select("*, document_profiles(name)")
        .order("document_profile_id")
        .order("block_kind")
        .execute()
    )

    routes = [
        ProfileRouteResponse(
            id=r["id"],
            document_profile_id=r["document_profile_id"],
            document_profile_name=(r.get("document_profiles") or {}).get("name"),
            block_kind=r["block_kind"],
            primary_source_id=r["primary_source_id"],
            primary_model_name=r["primary_model_name"],
            fallback_chain_json=r.get("fallback_chain_json") or [],
            default_prompt_template_id=r.get("default_prompt_template_id"),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in result.data or []
    ]

    return ProfileRouteListResponse(routes=routes)


@router.patch("/{route_id}", response_model=ProfileRouteResponse)
def update_default_prompt(
    route_id: str,
    body: ProfileRoutePatchRequest,
    user: CurrentUser = Depends(require_admin),
) -> ProfileRouteResponse:
    """Обновить default_prompt_template_id в profile route."""
    sb = get_supabase()

    # Проверить что шаблон существует и активен
    pt_result = (
        sb.table("prompt_templates")
        .select("id")
        .eq("id", body.default_prompt_template_id)
        .eq("is_active", True)
        .execute()
    )
    if not pt_result.data:
        raise HTTPException(status_code=400, detail="Prompt template не найден или не активен")

    result = (
        sb.table("profile_routes")
        .update({
            "default_prompt_template_id": body.default_prompt_template_id,
            "updated_by": user.id,
        })
        .eq("id", route_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Profile route не найден")

    r = result.data[0]
    # Загрузить имя профиля отдельно (update не поддерживает join)
    profile_result = (
        sb.table("document_profiles")
        .select("name")
        .eq("id", r["document_profile_id"])
        .execute()
    )
    profile_name = profile_result.data[0]["name"] if profile_result.data else None

    return ProfileRouteResponse(
        id=r["id"],
        document_profile_id=r["document_profile_id"],
        document_profile_name=profile_name,
        block_kind=r["block_kind"],
        primary_source_id=r["primary_source_id"],
        primary_model_name=r["primary_model_name"],
        fallback_chain_json=r.get("fallback_chain_json") or [],
        default_prompt_template_id=r.get("default_prompt_template_id"),
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )
