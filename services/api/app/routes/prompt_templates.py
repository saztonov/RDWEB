"""Prompt templates endpoints — CRUD, версионирование, usage.

Все эндпоинты требуют admin. prompt_templates — единственный
источник промптов для OCR (никаких config.yaml/settings.py).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from contracts import (
    PaginatedMeta,
    PromptTemplateCloneRequest,
    PromptTemplateCreateRequest,
    PromptTemplateListResponse,
    PromptTemplateNewVersionRequest,
    PromptTemplateResponse,
    PromptTemplateUsageResponse,
    PromptTemplateVersionsResponse,
    BlockRef,
    ProfileRouteRef,
)

from ..auth import CurrentUser, get_supabase
from ..auth.dependencies import require_admin

router = APIRouter(prefix="/prompt-templates", tags=["prompt-templates"])


def _row_to_response(row: dict) -> PromptTemplateResponse:
    """Преобразовать DB row в Pydantic response."""
    return PromptTemplateResponse(
        id=row["id"],
        template_key=row["template_key"],
        version=row["version"],
        is_active=row["is_active"],
        document_profile_id=row.get("document_profile_id"),
        block_kind=row["block_kind"],
        source_type=row["source_type"],
        model_pattern=row.get("model_pattern"),
        system_template=row["system_template"],
        user_template=row["user_template"],
        output_schema_json=row.get("output_schema_json"),
        parser_strategy=row["parser_strategy"],
        notes=row.get("notes"),
        created_by=row.get("created_by"),
        updated_by=row.get("updated_by"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ── LIST ─────────────────────────────────────────────────────────────────────


@router.get("/", response_model=PromptTemplateListResponse)
def list_prompt_templates(
    user: CurrentUser = Depends(require_admin),
    document_profile_id: str | None = Query(None),
    block_kind: str | None = Query(None),
    source_type: str | None = Query(None),
    model_pattern: str | None = Query(None),
    is_active: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PromptTemplateListResponse:
    """Список prompt templates с фильтрами."""
    sb = get_supabase()

    # Подсчёт
    count_q = sb.table("prompt_templates").select("id", count="exact")
    if document_profile_id:
        count_q = count_q.eq("document_profile_id", document_profile_id)
    if block_kind:
        count_q = count_q.eq("block_kind", block_kind)
    if source_type:
        count_q = count_q.eq("source_type", source_type)
    if model_pattern:
        count_q = count_q.ilike("model_pattern", f"%{model_pattern}%")
    if is_active is not None:
        count_q = count_q.eq("is_active", is_active)
    total = (count_q.execute()).count or 0

    # Данные
    data_q = (
        sb.table("prompt_templates")
        .select("*")
        .order("template_key")
        .order("version", desc=True)
        .range(offset, offset + limit - 1)
    )
    if document_profile_id:
        data_q = data_q.eq("document_profile_id", document_profile_id)
    if block_kind:
        data_q = data_q.eq("block_kind", block_kind)
    if source_type:
        data_q = data_q.eq("source_type", source_type)
    if model_pattern:
        data_q = data_q.ilike("model_pattern", f"%{model_pattern}%")
    if is_active is not None:
        data_q = data_q.eq("is_active", is_active)

    result = data_q.execute()
    templates = [_row_to_response(r) for r in result.data or []]

    return PromptTemplateListResponse(
        templates=templates,
        meta=PaginatedMeta(total=total, limit=limit, offset=offset),
    )


# ── GET ONE ──────────────────────────────────────────────────────────────────


@router.get("/{template_id}", response_model=PromptTemplateResponse)
def get_prompt_template(
    template_id: str,
    user: CurrentUser = Depends(require_admin),
) -> PromptTemplateResponse:
    """Один prompt template по ID."""
    sb = get_supabase()
    result = sb.table("prompt_templates").select("*").eq("id", template_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Prompt template не найден")
    return _row_to_response(result.data[0])


# ── CREATE ───────────────────────────────────────────────────────────────────


@router.post("/", response_model=PromptTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_prompt_template(
    body: PromptTemplateCreateRequest,
    user: CurrentUser = Depends(require_admin),
) -> PromptTemplateResponse:
    """Создать новый prompt template (version=1, is_active=false)."""
    sb = get_supabase()

    row = {
        "template_key": body.template_key,
        "version": 1,
        "is_active": False,
        "document_profile_id": body.document_profile_id,
        "block_kind": body.block_kind,
        "source_type": body.source_type,
        "model_pattern": body.model_pattern,
        "system_template": body.system_template,
        "user_template": body.user_template,
        "output_schema_json": body.output_schema_json,
        "parser_strategy": body.parser_strategy,
        "notes": body.notes,
        "created_by": user.id,
        "updated_by": user.id,
    }

    result = sb.table("prompt_templates").insert(row).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Не удалось создать prompt template")
    return _row_to_response(result.data[0])


# ── CLONE ────────────────────────────────────────────────────────────────────


@router.post("/{template_id}/clone", response_model=PromptTemplateResponse, status_code=status.HTTP_201_CREATED)
def clone_prompt_template(
    template_id: str,
    body: PromptTemplateCloneRequest | None = None,
    user: CurrentUser = Depends(require_admin),
) -> PromptTemplateResponse:
    """Клонировать шаблон с новым template_key."""
    sb = get_supabase()

    # Загрузить оригинал
    orig_result = sb.table("prompt_templates").select("*").eq("id", template_id).execute()
    if not orig_result.data:
        raise HTTPException(status_code=404, detail="Prompt template не найден")
    orig = orig_result.data[0]

    new_key = (body.new_template_key if body and body.new_template_key else f"{orig['template_key']}_copy")

    row = {
        "template_key": new_key,
        "version": 1,
        "is_active": False,
        "document_profile_id": orig.get("document_profile_id"),
        "block_kind": orig["block_kind"],
        "source_type": orig["source_type"],
        "model_pattern": orig.get("model_pattern"),
        "system_template": orig["system_template"],
        "user_template": orig["user_template"],
        "output_schema_json": orig.get("output_schema_json"),
        "parser_strategy": orig["parser_strategy"],
        "notes": f"Клон {orig['template_key']} v{orig['version']}",
        "created_by": user.id,
        "updated_by": user.id,
    }

    result = sb.table("prompt_templates").insert(row).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Не удалось клонировать prompt template")
    return _row_to_response(result.data[0])


# ── NEW VERSION ──────────────────────────────────────────────────────────────


@router.post(
    "/{template_id}/new-version",
    response_model=PromptTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_new_version(
    template_id: str,
    body: PromptTemplateNewVersionRequest,
    user: CurrentUser = Depends(require_admin),
) -> PromptTemplateResponse:
    """Создать новую версию шаблона (version=max+1, is_active=false)."""
    sb = get_supabase()

    # Загрузить исходный шаблон
    orig_result = sb.table("prompt_templates").select("*").eq("id", template_id).execute()
    if not orig_result.data:
        raise HTTPException(status_code=404, detail="Prompt template не найден")
    orig = orig_result.data[0]
    template_key = orig["template_key"]

    # Найти максимальную версию
    max_ver_result = (
        sb.table("prompt_templates")
        .select("version")
        .eq("template_key", template_key)
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    max_version = max_ver_result.data[0]["version"] if max_ver_result.data else 0

    row = {
        "template_key": template_key,
        "version": max_version + 1,
        "is_active": False,
        "document_profile_id": body.document_profile_id if body.document_profile_id is not None else orig.get("document_profile_id"),
        "block_kind": body.block_kind or orig["block_kind"],
        "source_type": body.source_type or orig["source_type"],
        "model_pattern": body.model_pattern if body.model_pattern is not None else orig.get("model_pattern"),
        "system_template": body.system_template,
        "user_template": body.user_template,
        "output_schema_json": body.output_schema_json if body.output_schema_json is not None else orig.get("output_schema_json"),
        "parser_strategy": body.parser_strategy or orig["parser_strategy"],
        "notes": body.notes if body.notes is not None else orig.get("notes"),
        "created_by": user.id,
        "updated_by": user.id,
    }

    result = sb.table("prompt_templates").insert(row).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Не удалось создать новую версию")
    return _row_to_response(result.data[0])


# ── ACTIVATE ─────────────────────────────────────────────────────────────────


@router.patch("/{template_id}/activate", response_model=PromptTemplateResponse)
def activate_prompt_template(
    template_id: str,
    user: CurrentUser = Depends(require_admin),
) -> PromptTemplateResponse:
    """Активировать версию (деактивировать остальные с тем же template_key)."""
    sb = get_supabase()

    # Загрузить шаблон
    orig_result = sb.table("prompt_templates").select("*").eq("id", template_id).execute()
    if not orig_result.data:
        raise HTTPException(status_code=404, detail="Prompt template не найден")
    template_key = orig_result.data[0]["template_key"]

    # Деактивировать все версии с этим ключом
    sb.table("prompt_templates").update({"is_active": False}).eq("template_key", template_key).execute()

    # Активировать выбранную версию
    result = (
        sb.table("prompt_templates")
        .update({"is_active": True, "updated_by": user.id})
        .eq("id", template_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Не удалось активировать prompt template")
    return _row_to_response(result.data[0])


# ── VERSIONS ─────────────────────────────────────────────────────────────────


@router.get("/by-key/{template_key}/versions", response_model=PromptTemplateVersionsResponse)
def get_versions(
    template_key: str,
    user: CurrentUser = Depends(require_admin),
) -> PromptTemplateVersionsResponse:
    """История версий по template_key."""
    sb = get_supabase()

    result = (
        sb.table("prompt_templates")
        .select("*")
        .eq("template_key", template_key)
        .order("version", desc=True)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail=f"Шаблоны с ключом '{template_key}' не найдены")

    versions = [_row_to_response(r) for r in result.data]
    return PromptTemplateVersionsResponse(template_key=template_key, versions=versions)


# ── USAGE ────────────────────────────────────────────────────────────────────


@router.get("/{template_id}/usage", response_model=PromptTemplateUsageResponse)
def get_usage(
    template_id: str,
    user: CurrentUser = Depends(require_admin),
) -> PromptTemplateUsageResponse:
    """Где используется шаблон: profile_routes и blocks с override."""
    sb = get_supabase()

    # Profile routes, ссылающиеся на этот шаблон
    pr_result = (
        sb.table("profile_routes")
        .select("id, block_kind, document_profile_id, document_profiles(name)")
        .eq("default_prompt_template_id", template_id)
        .execute()
    )
    profile_routes = [
        ProfileRouteRef(
            id=r["id"],
            document_profile_name=(r.get("document_profiles") or {}).get("name", "—"),
            block_kind=r["block_kind"],
        )
        for r in pr_result.data or []
    ]

    # Blocks с override на этот шаблон
    blocks_result = (
        sb.table("blocks")
        .select("id, block_kind, page_number, document_id, documents(title)")
        .eq("prompt_template_id", template_id)
        .is_("deleted_at", "null")
        .limit(100)
        .execute()
    )
    blocks = [
        BlockRef(
            id=r["id"],
            document_title=(r.get("documents") or {}).get("title", "—"),
            page_number=r["page_number"],
            block_kind=r["block_kind"],
        )
        for r in blocks_result.data or []
    ]

    return PromptTemplateUsageResponse(profile_routes=profile_routes, blocks=blocks)
