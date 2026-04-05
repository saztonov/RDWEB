"""Admin endpoints для block incidents — failed recognition attempts с контекстом."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from contracts import (
    BlockIncidentListResponse,
    BlockIncidentResponse,
    PaginatedMeta,
)

from ..auth import CurrentUser, get_supabase
from ..auth.dependencies import require_admin

router = APIRouter(prefix="/admin", tags=["admin-incidents"])


@router.get("/incidents", response_model=BlockIncidentListResponse)
def admin_list_incidents(
    user: CurrentUser = Depends(require_admin),
    error_code: str | None = Query(None),
    source_id: str | None = Query(None),
    document_id: str | None = Query(None),
    date_from: str | None = Query(None, description="ISO 8601 datetime"),
    date_to: str | None = Query(None, description="ISO 8601 datetime"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> BlockIncidentListResponse:
    """Failed recognition attempts с информацией о document/block/source."""
    sb = get_supabase()

    # Базовый запрос — failed/timeout attempts
    count_query = (
        sb.table("recognition_attempts")
        .select("id", count="exact")
        .in_("status", ["failed", "timeout"])
    )
    data_query = (
        sb.table("recognition_attempts")
        .select("*")
        .in_("status", ["failed", "timeout"])
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )

    # Фильтры
    if error_code:
        count_query = count_query.eq("error_code", error_code)
        data_query = data_query.eq("error_code", error_code)
    if source_id:
        count_query = count_query.eq("source_id", source_id)
        data_query = data_query.eq("source_id", source_id)
    if date_from:
        count_query = count_query.gte("created_at", date_from)
        data_query = data_query.gte("created_at", date_from)
    if date_to:
        count_query = count_query.lte("created_at", date_to)
        data_query = data_query.lte("created_at", date_to)

    count_result = count_query.execute()
    total = count_result.count or 0

    result = data_query.execute()
    attempts = result.data or []

    if not attempts:
        return BlockIncidentListResponse(
            incidents=[],
            meta=PaginatedMeta(total=total, limit=limit, offset=offset),
        )

    # Загрузить связанные блоки
    block_ids = list({a["block_id"] for a in attempts})
    blocks_result = (
        sb.table("blocks")
        .select("id, document_id, page_number, block_kind")
        .in_("id", block_ids)
        .execute()
    )
    blocks_map = {b["id"]: b for b in blocks_result.data or []}

    # Фильтр по document_id (на уровне блоков)
    if document_id:
        allowed_block_ids = {
            b["id"] for b in blocks_map.values() if b["document_id"] == document_id
        }
        attempts = [a for a in attempts if a["block_id"] in allowed_block_ids]

    # Загрузить document titles
    doc_ids = list({b["document_id"] for b in blocks_map.values()})
    doc_titles: dict[str, str] = {}
    if doc_ids:
        docs_result = sb.table("documents").select("id, title").in_("id", doc_ids).execute()
        doc_titles = {d["id"]: d["title"] for d in docs_result.data or []}

    # Загрузить source names
    source_ids = list({a["source_id"] for a in attempts if a.get("source_id")})
    source_names: dict[str, str] = {}
    if source_ids:
        sources_result = sb.table("ocr_sources").select("id, name").in_("id", source_ids).execute()
        source_names = {s["id"]: s["name"] for s in sources_result.data or []}

    incidents = []
    for att in attempts:
        block = blocks_map.get(att["block_id"], {})
        doc_id = block.get("document_id", "")

        incidents.append(BlockIncidentResponse(
            attempt_id=att["id"],
            run_id=att.get("run_id"),
            block_id=att["block_id"],
            document_id=doc_id,
            document_title=doc_titles.get(doc_id),
            page_number=block.get("page_number", 0),
            block_kind=block.get("block_kind", "text"),
            source_id=att.get("source_id"),
            source_name=source_names.get(att.get("source_id", ""), None),
            model_name=att.get("model_name"),
            prompt_template_id=att.get("prompt_template_id"),
            attempt_no=att.get("attempt_no", 1),
            fallback_no=att.get("fallback_no", 0),
            error_code=att.get("error_code"),
            error_message=att.get("error_message"),
            status=att["status"],
            created_at=att["created_at"],
        ))

    return BlockIncidentListResponse(
        incidents=incidents,
        meta=PaginatedMeta(total=total, limit=limit, offset=offset),
    )
