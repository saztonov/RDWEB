"""Общие schemas для API responses."""

from __future__ import annotations

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Стандартный формат ошибки."""

    detail: str


class PaginatedMeta(BaseModel):
    """Метаданные пагинации."""

    total: int
    limit: int
    offset: int
