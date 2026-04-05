"""Recognition endpoints — запуск распознавания, dirty detection, run status.

Endpoints:
- POST /documents/{id}/recognition/start — запуск recognition run
- GET  /documents/{id}/recognition/dirty — сводка dirty blocks
- GET  /documents/{id}/recognition/runs  — список recognition runs
- GET  /recognition/runs/{id}            — статус конкретного run
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from contracts import RecognitionRunCreateRequest

from ..auth import CurrentUser, get_current_user, get_supabase
from ..logging_config import get_logger
from ..permissions.checks import require_document_access
from ..services.dirty_detection import get_dirty_blocks
from ..services.recognition_service import start_recognition_run

_logger = get_logger(__name__)

router = APIRouter(tags=["recognition"])


# ──────────────────────────────────────────────────────────────────────
# POST /api/documents/{document_id}/recognition/start
# ──────────────────────────────────────────────────────────────────────

@router.post("/documents/{document_id}/recognition/start")
def start_recognition(
    document_id: str,
    body: RecognitionRunCreateRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Запуск recognition run (smart / full / block_rerun)."""
    require_document_access(document_id, user)
    sb = get_supabase()

    try:
        result = start_recognition_run(
            document_id=document_id,
            run_mode=body.run_mode,
            user_id=user.id,
            sb=sb,
            block_ids=body.block_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "run": result["run"],
        "target_block_ids": result["target_block_ids"],
    }


# ──────────────────────────────────────────────────────────────────────
# GET /api/documents/{document_id}/recognition/dirty
# ──────────────────────────────────────────────────────────────────────

@router.get("/documents/{document_id}/recognition/dirty")
def dirty_summary(
    document_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Сводка dirty-блоков документа для smart rerun."""
    require_document_access(document_id, user)
    sb = get_supabase()

    dirty = get_dirty_blocks(document_id, sb)
    return {
        "total": dirty.total,
        "dirty_count": dirty.dirty_count,
        "locked_count": dirty.locked_count,
        "dirty_block_ids": dirty.dirty_block_ids,
    }


# ──────────────────────────────────────────────────────────────────────
# GET /api/documents/{document_id}/recognition/runs
# ──────────────────────────────────────────────────────────────────────

@router.get("/documents/{document_id}/recognition/runs")
def list_recognition_runs(
    document_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Список recognition runs документа."""
    require_document_access(document_id, user)
    sb = get_supabase()

    result = (
        sb.table("recognition_runs")
        .select("*")
        .eq("document_id", document_id)
        .order("created_at", desc=True)
        .execute()
    )
    return {"runs": result.data or []}


# ──────────────────────────────────────────────────────────────────────
# GET /api/recognition/runs/{run_id}
# ──────────────────────────────────────────────────────────────────────

@router.get("/recognition/runs/{run_id}")
def get_run_status(
    run_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Статус конкретного recognition run с прогрессом."""
    sb = get_supabase()

    result = (
        sb.table("recognition_runs")
        .select("*")
        .eq("id", run_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Recognition run не найден")

    # Проверка доступа через документ
    require_document_access(result.data["document_id"], user)

    return result.data
