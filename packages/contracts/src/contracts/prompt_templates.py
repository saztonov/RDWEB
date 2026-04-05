"""Schemas для prompt templates, profile routes и block prompt override."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from .common import PaginatedMeta


# ── Enum ─────────────────────────────────────────────────────────────────────

class ParserStrategy(StrEnum):
    """Зеркало DB enum parser_strategy."""

    PLAIN_TEXT = "plain_text"
    STAMP_JSON = "stamp_json"
    IMAGE_JSON = "image_json"
    HTML_FRAGMENT = "html_fragment"


# ── Prompt Template ──────────────────────────────────────────────────────────

class PromptTemplateResponse(BaseModel):
    """Полное представление prompt template."""

    id: str
    template_key: str
    version: int
    is_active: bool
    document_profile_id: str | None = None
    block_kind: str
    source_type: str
    model_pattern: str | None = None
    system_template: str
    user_template: str
    output_schema_json: dict | None = None
    parser_strategy: str
    notes: str | None = None
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime
    updated_at: datetime


class PromptTemplateListResponse(BaseModel):
    """Пагинированный список prompt templates."""

    templates: list[PromptTemplateResponse]
    meta: PaginatedMeta


class PromptTemplateCreateRequest(BaseModel):
    """Создание нового prompt template (version=1)."""

    template_key: str
    document_profile_id: str | None = None
    block_kind: str
    source_type: str
    model_pattern: str | None = None
    system_template: str
    user_template: str
    output_schema_json: dict | None = None
    parser_strategy: str = "plain_text"
    notes: str | None = None


class PromptTemplateCloneRequest(BaseModel):
    """Клонирование шаблона с новым template_key."""

    new_template_key: str | None = None


class PromptTemplateNewVersionRequest(BaseModel):
    """Создание новой версии — все поля можно изменить кроме template_key."""

    system_template: str
    user_template: str
    document_profile_id: str | None = None
    block_kind: str | None = None
    source_type: str | None = None
    model_pattern: str | None = None
    output_schema_json: dict | None = None
    parser_strategy: str | None = None
    notes: str | None = None


class PromptTemplateVersionsResponse(BaseModel):
    """История версий по template_key."""

    template_key: str
    versions: list[PromptTemplateResponse]


# ── Usage ────────────────────────────────────────────────────────────────────

class ProfileRouteRef(BaseModel):
    """Ссылка на profile_route, использующий шаблон."""

    id: str
    document_profile_name: str
    block_kind: str


class BlockRef(BaseModel):
    """Ссылка на block с override на шаблон."""

    id: str
    document_title: str
    page_number: int
    block_kind: str


class PromptTemplateUsageResponse(BaseModel):
    """Где используется данный шаблон."""

    profile_routes: list[ProfileRouteRef]
    blocks: list[BlockRef]


# ── Profile Routes ───────────────────────────────────────────────────────────

class ProfileRouteResponse(BaseModel):
    """Представление profile_route."""

    id: str
    document_profile_id: str
    document_profile_name: str | None = None
    block_kind: str
    primary_source_id: str
    primary_model_name: str
    fallback_chain_json: list = []
    default_prompt_template_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ProfileRouteListResponse(BaseModel):
    """Список profile routes."""

    routes: list[ProfileRouteResponse]


class ProfileRoutePatchRequest(BaseModel):
    """Обновление default prompt template в profile route."""

    default_prompt_template_id: str


# ── Block Prompt Override ────────────────────────────────────────────────────

class BlockPromptOverrideRequest(BaseModel):
    """Установка/удаление block-level prompt template override."""

    prompt_template_id: str | None = None
