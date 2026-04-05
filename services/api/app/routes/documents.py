"""Document endpoints — список, детали, ingestion (upload/finalize/download)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from contracts import (
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentPageResponse,
    DocumentResponse,
    DownloadUrlResponse,
    FinalizeRequest,
    FinalizeResponse,
    PagesListResponse,
    PaginatedMeta,
    UploadUrlRequest,
    UploadUrlResponse,
)

from ..auth import CurrentUser, get_current_user, get_supabase
from ..permissions.checks import require_document_access, require_workspace_member
from ..services import document_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/", response_model=DocumentListResponse)
def list_documents(
    workspace_id: str = Query(..., description="ID workspace-а"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: CurrentUser = Depends(get_current_user),
) -> DocumentListResponse:
    """Список документов в workspace. Проверяет membership."""
    require_workspace_member(workspace_id, user)

    sb = get_supabase()

    # Получить общее количество
    count_result = (
        sb.table("documents")
        .select("id", count="exact")
        .eq("workspace_id", workspace_id)
        .execute()
    )
    total = count_result.count or 0

    # Получить документы с пагинацией
    result = (
        sb.table("documents")
        .select("*")
        .eq("workspace_id", workspace_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )

    documents = [
        DocumentResponse(
            id=row["id"],
            workspace_id=row["workspace_id"],
            title=row["title"],
            status=row["status"],
            page_count=row.get("page_count") or 0,
            created_by=row.get("created_by"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in result.data or []
    ]

    return DocumentListResponse(
        documents=documents,
        meta=PaginatedMeta(total=total, limit=limit, offset=offset),
    )


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(
    document_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> DocumentDetailResponse:
    """Детали документа с pages и block-статистикой. Проверяет доступ через workspace."""
    require_document_access(document_id, user)

    sb = get_supabase()

    # Документ
    doc_result = sb.table("documents").select("*").eq("id", document_id).single().execute()
    doc = doc_result.data

    # Страницы
    pages_result = (
        sb.table("document_pages")
        .select("*")
        .eq("document_id", document_id)
        .order("page_number")
        .execute()
    )
    pages = [
        DocumentPageResponse(
            id=row["id"],
            page_number=row["page_number"],
            width=row["width"],
            height=row["height"],
            rotation=row.get("rotation") or 0,
        )
        for row in pages_result.data or []
    ]

    # Block-статистика
    blocks_result = (
        sb.table("blocks")
        .select("id", count="exact")
        .eq("document_id", document_id)
        .is_("deleted_at", "null")
        .execute()
    )
    blocks_count = blocks_result.count or 0

    recognized_result = (
        sb.table("blocks")
        .select("id", count="exact")
        .eq("document_id", document_id)
        .eq("current_status", "recognized")
        .is_("deleted_at", "null")
        .execute()
    )
    recognized_count = recognized_result.count or 0

    failed_result = (
        sb.table("blocks")
        .select("id", count="exact")
        .eq("document_id", document_id)
        .eq("current_status", "failed")
        .is_("deleted_at", "null")
        .execute()
    )
    failed_count = failed_result.count or 0

    return DocumentDetailResponse(
        id=doc["id"],
        workspace_id=doc["workspace_id"],
        title=doc["title"],
        status=doc["status"],
        page_count=doc.get("page_count") or 0,
        created_by=doc.get("created_by"),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
        pages=pages,
        blocks_count=blocks_count,
        recognized_count=recognized_count,
        failed_count=failed_count,
    )


# ─── Ingestion endpoints ─────────────────────────────────────────────────────


@router.post("/upload-url", response_model=UploadUrlResponse)
def create_upload_url(
    body: UploadUrlRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> UploadUrlResponse:
    """Сгенерировать presigned PUT URL для прямой загрузки PDF в R2.

    Frontend получает URL и грузит PDF напрямую в R2,
    минуя backend как байтовый прокси.
    """
    require_workspace_member(body.workspace_id, user)
    r2 = request.app.state.r2_client
    result = document_service.create_upload(
        workspace_id=body.workspace_id,
        title=body.title,
        r2=r2,
        created_by=user.id,
    )
    return UploadUrlResponse(**result)


@router.post("/finalize", response_model=FinalizeResponse)
def finalize_upload(
    body: FinalizeRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> FinalizeResponse:
    """Финализировать загрузку: проверить PDF в R2, извлечь page metadata.

    Извлекает page_count, page sizes, rotation и сохраняет в document_pages.
    Для MVP overwrite original PDF запрещён — повторный finalize даёт 409.
    """
    require_document_access(body.document_id, user)
    r2 = request.app.state.r2_client
    pdf_cache = request.app.state.pdf_cache
    result = document_service.finalize(
        document_id=body.document_id,
        r2=r2,
        pdf_cache=pdf_cache,
    )
    return FinalizeResponse(**result)


@router.get("/{document_id}/pages", response_model=PagesListResponse)
def get_pages(
    document_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> PagesListResponse:
    """Список страниц документа с метаданными (width, height, rotation)."""
    require_document_access(document_id, user)

    sb = get_supabase()
    pages_result = (
        sb.table("document_pages")
        .select("*")
        .eq("document_id", document_id)
        .order("page_number")
        .execute()
    )
    pages = [
        DocumentPageResponse(
            id=row["id"],
            page_number=row["page_number"],
            width=row["width"],
            height=row["height"],
            rotation=row.get("rotation") or 0,
        )
        for row in pages_result.data or []
    ]
    return PagesListResponse(document_id=document_id, pages=pages)


@router.get("/{document_id}/download-url", response_model=DownloadUrlResponse)
def get_download_url(
    document_id: str,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> DownloadUrlResponse:
    """Presigned GET URL для скачивания оригинального PDF из R2."""
    require_document_access(document_id, user)
    r2 = request.app.state.r2_client
    result = document_service.get_download_url(document_id=document_id, r2=r2)
    return DownloadUrlResponse(**result)
