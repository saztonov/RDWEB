"""Admin endpoints для recognition runs — список, детали, блоки."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from contracts import (
    AdminRunBlockResponse,
    AdminRunDetailResponse,
    AdminRunListResponse,
    AdminRunResponse,
    PaginatedMeta,
)

from ..auth import CurrentUser, get_supabase
from ..auth.dependencies import require_admin

router = APIRouter(prefix="/admin", tags=["admin-runs"])


def _run_to_response(row: dict, doc_title: str | None = None) -> AdminRunResponse:
    return AdminRunResponse(
        id=row["id"],
        document_id=row["document_id"],
        document_title=doc_title,
        initiated_by=row.get("initiated_by"),
        run_mode=row["run_mode"],
        status=row["status"],
        total_blocks=row.get("total_blocks", 0),
        dirty_blocks=row.get("dirty_blocks", 0),
        processed_blocks=row.get("processed_blocks", 0),
        recognized_blocks=row.get("recognized_blocks", 0),
        failed_blocks=row.get("failed_blocks", 0),
        manual_review_blocks=row.get("manual_review_blocks", 0),
        started_at=row.get("started_at"),
        finished_at=row.get("finished_at"),
        created_at=row["created_at"],
    )


@router.get("/runs", response_model=AdminRunListResponse)
def admin_list_runs(
    user: CurrentUser = Depends(require_admin),
    status: str | None = Query(None),
    document_id: str | None = Query(None),
    date_from: str | None = Query(None, description="ISO 8601 datetime"),
    date_to: str | None = Query(None, description="ISO 8601 datetime"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AdminRunListResponse:
    """Пагинированный список recognition runs cross-document."""
    sb = get_supabase()

    # Счётчик
    count_query = sb.table("recognition_runs").select("id", count="exact")
    if status:
        count_query = count_query.eq("status", status)
    if document_id:
        count_query = count_query.eq("document_id", document_id)
    if date_from:
        count_query = count_query.gte("created_at", date_from)
    if date_to:
        count_query = count_query.lte("created_at", date_to)
    count_result = count_query.execute()
    total = count_result.count or 0

    # Данные
    query = (
        sb.table("recognition_runs")
        .select("*")
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if status:
        query = query.eq("status", status)
    if document_id:
        query = query.eq("document_id", document_id)
    if date_from:
        query = query.gte("created_at", date_from)
    if date_to:
        query = query.lte("created_at", date_to)
    result = query.execute()

    # Получить document titles
    doc_ids = list({r["document_id"] for r in result.data or []})
    doc_titles: dict[str, str] = {}
    if doc_ids:
        docs_result = sb.table("documents").select("id, title").in_("id", doc_ids).execute()
        doc_titles = {d["id"]: d["title"] for d in docs_result.data or []}

    runs = [
        _run_to_response(row, doc_titles.get(row["document_id"]))
        for row in result.data or []
    ]

    return AdminRunListResponse(
        runs=runs,
        meta=PaginatedMeta(total=total, limit=limit, offset=offset),
    )


@router.get("/runs/{run_id}", response_model=AdminRunDetailResponse)
def admin_run_detail(
    run_id: str,
    user: CurrentUser = Depends(require_admin),
) -> AdminRunDetailResponse:
    """Детали recognition run-а с блоками."""
    sb = get_supabase()

    # Run
    run_result = sb.table("recognition_runs").select("*").eq("id", run_id).maybe_single().execute()
    if not run_result.data:
        raise HTTPException(status_code=404, detail="Recognition run не найден")
    run = run_result.data

    # Document title
    doc_result = sb.table("documents").select("title").eq("id", run["document_id"]).maybe_single().execute()
    doc_title = doc_result.data["title"] if doc_result.data else None

    # Блоки run-а (через recognition_attempts)
    attempts_result = (
        sb.table("recognition_attempts")
        .select("block_id, status, error_code, error_message")
        .eq("run_id", run_id)
        .execute()
    )

    # Уникальные block_ids
    block_ids = list({a["block_id"] for a in attempts_result.data or []})

    blocks_data: list[AdminRunBlockResponse] = []
    if block_ids:
        blocks_result = (
            sb.table("blocks")
            .select("id, page_number, block_kind, current_status")
            .in_("id", block_ids)
            .order("page_number")
            .execute()
        )

        # Подсчёт attempts и последняя ошибка для каждого блока
        block_attempts: dict[str, list[dict]] = {}
        for a in attempts_result.data or []:
            block_attempts.setdefault(a["block_id"], []).append(a)

        for b in blocks_result.data or []:
            bid = b["id"]
            att_list = block_attempts.get(bid, [])
            last_error = None
            for att in att_list:
                if att.get("error_message"):
                    last_error = att["error_message"]
                    break

            blocks_data.append(AdminRunBlockResponse(
                block_id=bid,
                page_number=b["page_number"],
                block_kind=b["block_kind"],
                current_status=b["current_status"],
                attempt_count=len(att_list),
                last_error=last_error,
            ))

    return AdminRunDetailResponse(
        id=run["id"],
        document_id=run["document_id"],
        document_title=doc_title,
        initiated_by=run.get("initiated_by"),
        run_mode=run["run_mode"],
        status=run["status"],
        total_blocks=run.get("total_blocks", 0),
        dirty_blocks=run.get("dirty_blocks", 0),
        processed_blocks=run.get("processed_blocks", 0),
        recognized_blocks=run.get("recognized_blocks", 0),
        failed_blocks=run.get("failed_blocks", 0),
        manual_review_blocks=run.get("manual_review_blocks", 0),
        started_at=run.get("started_at"),
        finished_at=run.get("finished_at"),
        created_at=run["created_at"],
        blocks=blocks_data,
    )
