"""Export endpoints — генерация и скачивание итоговых документов.

Export строится ТОЛЬКО из current state блоков в БД (правило #5, #16 пролога).
Синхронная генерация — документы небольшие, Celery не нужен.
"""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from contracts import ExportCreateRequest, ExportListResponse, ExportResponse

from ..auth import CurrentUser, get_current_user
from ..permissions.checks import require_document_access
from ..services import export_service

router = APIRouter(prefix="/documents/{document_id}/exports", tags=["exports"])


@router.post("")
def create_export(
    document_id: str,
    body: ExportCreateRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """Сгенерировать и скачать export документа (HTML или Markdown).

    Файл генерируется на лету из текущего состояния блоков в БД.
    Metadata экспорта сохраняется в document_exports для истории.
    """
    require_document_access(document_id, user)

    r2_client = getattr(request.app.state, "r2_client", None)

    content_bytes, file_name, content_type, _export_record = (
        export_service.create_export(
            document_id=document_id,
            output_format=body.output_format,
            include_crop_links=body.include_crop_links,
            include_stamp_info=body.include_stamp_info,
            r2_client=r2_client,
        )
    )

    return StreamingResponse(
        io.BytesIO(content_bytes),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Content-Length": str(len(content_bytes)),
        },
    )


@router.get("", response_model=ExportListResponse)
def list_exports(
    document_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> ExportListResponse:
    """Получить историю экспортов документа."""
    require_document_access(document_id, user)

    rows = export_service.list_exports(document_id)
    exports = [
        ExportResponse(
            id=row["id"],
            document_id=row["document_id"],
            export_format=row["export_format"],
            options_json=row.get("options_json"),
            file_name=row.get("file_name"),
            file_size=row.get("file_size"),
            status=row["status"],
            error_message=row.get("error_message"),
            created_at=row["created_at"],
            completed_at=row.get("completed_at"),
        )
        for row in rows
    ]
    return ExportListResponse(exports=exports)


@router.get("/{export_id}", response_model=ExportResponse)
def get_export(
    document_id: str,
    export_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> ExportResponse:
    """Получить metadata конкретного экспорта."""
    require_document_access(document_id, user)

    row = export_service.get_export(document_id, export_id)
    if not row:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Экспорт не найден")

    return ExportResponse(
        id=row["id"],
        document_id=row["document_id"],
        export_format=row["export_format"],
        options_json=row.get("options_json"),
        file_name=row.get("file_name"),
        file_size=row.get("file_size"),
        status=row["status"],
        error_message=row.get("error_message"),
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
    )
