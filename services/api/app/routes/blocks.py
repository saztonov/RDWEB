"""Block endpoints — CRUD + restore для блоков документа.

Правила обновления:
- изменение bbox_json/polygon_json → geometry_rev + 1
- изменение route_source_id/route_model_name/prompt_template_id → dirty (обнуление last_recognition_signature)
- manual text editing — не в этом этапе
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..auth import CurrentUser, get_current_user, get_supabase
from ..logging_config import get_logger
from ..permissions.checks import require_document_access

_logger = get_logger(__name__)

router = APIRouter(tags=["blocks"])


# ──────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────

class BboxJson(BaseModel):
    """Bounding box в координатах страницы."""
    x: float
    y: float
    width: float
    height: float


class CreateBlockRequest(BaseModel):
    """Payload для создания блока."""
    block_kind: str = Field(..., pattern=r"^(text|stamp|image)$")
    shape_type: str = Field("rect", pattern=r"^(rect|polygon)$")
    page_number: int = Field(..., ge=1)
    bbox_json: BboxJson
    polygon_json: list[list[float]] | None = None


class UpdateBlockRequest(BaseModel):
    """Payload для обновления блока. Все поля опциональны."""
    bbox_json: BboxJson | None = None
    polygon_json: list[list[float]] | None = None
    shape_type: str | None = Field(None, pattern=r"^(rect|polygon)$")
    route_source_id: str | None = None
    route_model_name: str | None = None
    prompt_template_id: str | None = None


def _serialize_block(row: dict) -> dict:
    """Привести строку из Supabase к API-формату."""
    return {
        "id": row["id"],
        "document_id": row["document_id"],
        "page_number": row["page_number"],
        "block_kind": row["block_kind"],
        "shape_type": row["shape_type"],
        "bbox_json": row["bbox_json"],
        "polygon_json": row.get("polygon_json"),
        "reading_order": row.get("reading_order"),
        "geometry_rev": row["geometry_rev"],
        "content_rev": row["content_rev"],
        "manual_lock": row["manual_lock"],
        "route_source_id": row.get("route_source_id"),
        "route_model_name": row.get("route_model_name"),
        "prompt_template_id": row.get("prompt_template_id"),
        "current_text": row.get("current_text"),
        "current_status": row["current_status"],
        "deleted_at": row.get("deleted_at"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ──────────────────────────────────────────────────────────────────────
# GET /api/documents/{document_id}/blocks?page=N
# ───────────────────────────���──────────────────────────────────────────

@router.get("/documents/{document_id}/blocks")
def list_blocks(
    document_id: str,
    page: int = Query(..., ge=1, description="Номер страницы"),
    include_deleted: bool = Query(False, description="Включить soft-deleted блоки"),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Блоки указанной страницы документа."""
    require_document_access(document_id, user)

    sb = get_supabase()
    query = (
        sb.table("blocks")
        .select("*")
        .eq("document_id", document_id)
        .eq("page_number", page)
        .order("reading_order", desc=False, nullsfirst=False)
        .order("created_at", desc=False)
    )

    if not include_deleted:
        query = query.is_("deleted_at", "null")

    result = query.execute()
    blocks = [_serialize_block(row) for row in (result.data or [])]
    return {"blocks": blocks}


# ──────────────────────────────────────────────────────────────────────
# POST /api/documents/{document_id}/blocks
# ───────────────��──────────────────────────────────────────────────────

@router.post("/documents/{document_id}/blocks", status_code=status.HTTP_201_CREATED)
def create_block(
    document_id: str,
    body: CreateBlockRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Создать блок. Валидация: один stamp на страницу."""
    require_document_access(document_id, user)

    sb = get_supabase()

    # Валидация: один stamp на страницу
    if body.block_kind == "stamp":
        existing = (
            sb.table("blocks")
            .select("id", count="exact")
            .eq("document_id", document_id)
            .eq("page_number", body.page_number)
            .eq("block_kind", "stamp")
            .is_("deleted_at", "null")
            .execute()
        )
        if (existing.count or 0) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="На этой странице уже есть блок stamp. Допускается только один stamp на страницу.",
            )

    # Определить reading_order (следующий после максимального)
    max_order_result = (
        sb.table("blocks")
        .select("reading_order")
        .eq("document_id", document_id)
        .eq("page_number", body.page_number)
        .is_("deleted_at", "null")
        .order("reading_order", desc=True, nullsfirst=False)
        .limit(1)
        .execute()
    )
    next_order = 1
    if max_order_result.data and max_order_result.data[0].get("reading_order") is not None:
        next_order = max_order_result.data[0]["reading_order"] + 1

    insert_data: dict[str, Any] = {
        "document_id": document_id,
        "page_number": body.page_number,
        "block_kind": body.block_kind,
        "shape_type": body.shape_type,
        "bbox_json": body.bbox_json.model_dump(),
        "polygon_json": body.polygon_json,
        "reading_order": next_order,
        "created_by": user.id,
        "updated_by": user.id,
    }

    result = sb.table("blocks").insert(insert_data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Не удалось создать блок")

    _logger.info(
        "Block created",
        extra={
            "event": "block_created",
            "block_id": result.data[0]["id"],
            "document_id": document_id,
            "page": body.page_number,
            "kind": body.block_kind,
            "user_id": user.id,
        },
    )

    return _serialize_block(result.data[0])


# ──────────���───────────────────────────────────────────────────────────
# PATCH /api/blocks/{block_id}
# ───���──────────────────────────────────────────────────────────────────

@router.patch("/blocks/{block_id}")
def update_block(
    block_id: str,
    body: UpdateBlockRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Обновить блок.

    Правила:
    - bbox_json/polygon_json изменены → geometry_rev + 1
    - route_source_id/route_model_name/prompt_template_id → dirty (обнуление signature)
    """
    sb = get_supabase()

    # Получить текущий блок
    block_result = sb.table("blocks").select("*").eq("id", block_id).is_("deleted_at", "null").single().execute()
    block = block_result.data
    if not block:
        raise HTTPException(status_code=404, detail="Блок не найден")

    # Проверка доступа через документ
    require_document_access(block["document_id"], user)

    update_data: dict[str, Any] = {"updated_by": user.id}
    geometry_changed = False
    route_changed = False

    if body.bbox_json is not None:
        update_data["bbox_json"] = body.bbox_json.model_dump()
        geometry_changed = True

    if body.polygon_json is not None:
        update_data["polygon_json"] = body.polygon_json
        geometry_changed = True

    if body.shape_type is not None:
        update_data["shape_type"] = body.shape_type

    if body.route_source_id is not None:
        update_data["route_source_id"] = body.route_source_id
        route_changed = True

    if body.route_model_name is not None:
        update_data["route_model_name"] = body.route_model_name
        route_changed = True

    if body.prompt_template_id is not None:
        update_data["prompt_template_id"] = body.prompt_template_id
        route_changed = True

    # geometry_rev + 1 при изменении геометрии
    if geometry_changed:
        update_data["geometry_rev"] = block["geometry_rev"] + 1

    # Пометка dirty при изменении route/model/prompt
    if route_changed:
        update_data["last_recognition_signature"] = None

    result = sb.table("blocks").update(update_data).eq("id", block_id).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Не удалось обновить блок")

    _logger.info(
        "Block updated",
        extra={
            "event": "block_updated",
            "block_id": block_id,
            "geometry_changed": geometry_changed,
            "route_changed": route_changed,
            "user_id": user.id,
        },
    )

    return _serialize_block(result.data[0])


# ────────────────────────��─────────────────────────────────────────────
# DELETE /api/blocks/{block_id}
# ────────────────────────���────────────────────────────���────────────────

@router.delete("/blocks/{block_id}", status_code=status.HTTP_200_OK)
def delete_block(
    block_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Soft delete блока — устанавливает deleted_at."""
    sb = get_supabase()

    # Получить блок
    block_result = sb.table("blocks").select("document_id").eq("id", block_id).is_("deleted_at", "null").maybe_single().execute()
    if not block_result.data:
        raise HTTPException(status_code=404, detail="Блок не найден")

    require_document_access(block_result.data["document_id"], user)

    now = datetime.now(timezone.utc).isoformat()
    sb.table("blocks").update({
        "deleted_at": now,
        "updated_by": user.id,
    }).eq("id", block_id).execute()

    _logger.info("Block soft-deleted", extra={"event": "block_deleted", "block_id": block_id, "user_id": user.id})

    return {"ok": True}


# ────────────────���──────────────────────────��──────────────────────────
# POST /api/blocks/{block_id}/restore
# ───────────��──────────────────────────────────────────────────────────

@router.post("/blocks/{block_id}/restore")
def restore_block(
    block_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Восстановить soft-deleted блок."""
    sb = get_supabase()

    # Получить блок (включая deleted)
    block_result = sb.table("blocks").select("*").eq("id", block_id).not_.is_("deleted_at", "null").maybe_single().execute()
    if not block_result.data:
        raise HTTPException(status_code=404, detail="Удалённый блок не найден")

    require_document_access(block_result.data["document_id"], user)

    # Валидация: если stamp — проверить что нет другого stamp на этой странице
    block = block_result.data
    if block["block_kind"] == "stamp":
        existing = (
            sb.table("blocks")
            .select("id", count="exact")
            .eq("document_id", block["document_id"])
            .eq("page_number", block["page_number"])
            .eq("block_kind", "stamp")
            .is_("deleted_at", "null")
            .execute()
        )
        if (existing.count or 0) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="На странице уже есть stamp. Удалите его перед восстановлением.",
            )

    result = (
        sb.table("blocks")
        .update({"deleted_at": None, "updated_by": user.id})
        .eq("id", block_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=500, detail="Не удалось восстановить блок")

    _logger.info("Block restored", extra={"event": "block_restored", "block_id": block_id, "user_id": user.id})

    return _serialize_block(result.data[0])
