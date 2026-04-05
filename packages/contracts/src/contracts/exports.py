"""Schemas для export endpoints — генерация итоговых документов."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ExportCreateRequest(BaseModel):
    """Запрос на создание экспорта документа."""

    output_format: Literal["html", "markdown"] = Field(
        ..., description="Формат выходного файла"
    )
    include_crop_links: bool = Field(
        True, description="Вставлять ссылки на crop изображения блоков"
    )
    include_stamp_info: bool = Field(
        True, description="Прокидывать информацию из stamp блоков в остальные"
    )


class ExportResponse(BaseModel):
    """Метаданные одного экспорта."""

    id: str
    document_id: str
    export_format: str
    options_json: dict | None = None
    file_name: str | None = None
    file_size: int | None = None
    status: str
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ExportListResponse(BaseModel):
    """Список экспортов документа."""

    exports: list[ExportResponse]
