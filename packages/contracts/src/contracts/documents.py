"""Schemas для document endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .common import PaginatedMeta


# ─── Запросы на ingestion ─────────────────────────────────────────────────────


class UploadUrlRequest(BaseModel):
    """Запрос presigned URL для загрузки PDF в R2."""

    workspace_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=500)


class FinalizeRequest(BaseModel):
    """Подтверждение завершения загрузки PDF."""

    document_id: str = Field(..., min_length=1)


# ─── Ответы на ingestion ─────────────────────────────────────────────────────


class UploadUrlResponse(BaseModel):
    """Presigned PUT URL и метаданные для фронтенда."""

    document_id: str
    upload_url: str
    r2_key: str


class FinalizeResponse(BaseModel):
    """Результат финализации документа."""

    document_id: str
    status: str
    page_count: int


class DownloadUrlResponse(BaseModel):
    """Presigned GET URL для скачивания оригинала."""

    download_url: str
    expires_in: int


# ─── Общие ответы ─────────────────────────────────────────────────────────────


class DocumentPageResponse(BaseModel):
    """Страница документа."""

    id: str
    page_number: int
    width: int
    height: int
    rotation: int = 0


class DocumentResponse(BaseModel):
    """Документ в списке."""

    id: str
    workspace_id: str
    title: str
    status: str
    page_count: int = 0
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentDetailResponse(DocumentResponse):
    """Детали документа с pages и block-статистикой."""

    pages: list[DocumentPageResponse] = []
    blocks_count: int = 0
    recognized_count: int = 0
    failed_count: int = 0


class PagesListResponse(BaseModel):
    """Список страниц документа."""

    document_id: str
    pages: list[DocumentPageResponse]


class DocumentListResponse(BaseModel):
    """Пагинированный список документов."""

    documents: list[DocumentResponse]
    meta: PaginatedMeta
