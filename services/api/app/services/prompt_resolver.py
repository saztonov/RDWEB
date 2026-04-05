"""Runtime-сервис для resolve prompt template при OCR.

Логика:
1. block.prompt_template_id (block-level override) — приоритет
2. profile_routes.default_prompt_template_id — fallback
3. Подстановка template variables
4. Формирование snapshot для recognition_attempts

Вызывается из OCR worker'а, НЕ из API endpoint'а.
Frontend никогда не отправляет raw prompt text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..auth.supabase_client import get_supabase
from ..logging_config import get_logger

_logger = get_logger(__name__)

# Список поддерживаемых template variables
TEMPLATE_VARIABLES = {
    "DOC_NAME", "PAGE_NUM", "BLOCK_ID", "BLOCK_KIND",
    "OPERATOR_HINT", "PDF_TEXT", "SOURCE_NAME", "MODEL_NAME",
}


@dataclass(frozen=True)
class PromptContext:
    """Контекст для подстановки template variables."""

    doc_name: str = ""
    page_num: int = 0
    block_id: str = ""
    block_kind: str = ""
    operator_hint: str = ""
    pdf_text: str = ""
    source_name: str = ""
    model_name: str = ""

    def as_dict(self) -> dict[str, str]:
        """Словарь для подстановки в шаблон."""
        return {
            "DOC_NAME": self.doc_name,
            "PAGE_NUM": str(self.page_num),
            "BLOCK_ID": self.block_id,
            "BLOCK_KIND": self.block_kind,
            "OPERATOR_HINT": self.operator_hint,
            "PDF_TEXT": self.pdf_text,
            "SOURCE_NAME": self.source_name,
            "MODEL_NAME": self.model_name,
        }


@dataclass(frozen=True)
class ResolvedPrompt:
    """Результат resolve — готовые к отправке промпты + snapshot."""

    system_prompt: str
    user_prompt: str
    parser_strategy: str
    output_schema_json: dict[str, Any] | None
    template_id: str
    snapshot_json: dict[str, Any]


def _substitute_variables(template: str, variables: dict[str, str]) -> str:
    """Безопасная подстановка {VARIABLE} в шаблон.

    Неизвестные переменные остаются как есть (не вызывают ошибку).
    """
    def replacer(match: re.Match) -> str:
        key = match.group(1)
        return variables.get(key, match.group(0))

    return re.sub(r"\{([A-Z_]+)\}", replacer, template)


def resolve_prompt(
    block_id: str,
    document_profile_id: str,
    block_kind: str,
    context: PromptContext,
) -> ResolvedPrompt:
    """Resolve prompt template для блока.

    Приоритет:
    1. block.prompt_template_id (block-level override)
    2. profile_routes.default_prompt_template_id
    """
    sb = get_supabase()

    # 1. Проверить block-level override
    block_result = (
        sb.table("blocks")
        .select("prompt_template_id")
        .eq("id", block_id)
        .execute()
    )
    template_id = None
    if block_result.data:
        template_id = block_result.data[0].get("prompt_template_id")

    # 2. Fallback → profile_routes
    if not template_id:
        route_result = (
            sb.table("profile_routes")
            .select("default_prompt_template_id")
            .eq("document_profile_id", document_profile_id)
            .eq("block_kind", block_kind)
            .execute()
        )
        if route_result.data:
            template_id = route_result.data[0].get("default_prompt_template_id")

    if not template_id:
        raise ValueError(
            f"Не удалось resolve prompt template: block_id={block_id}, "
            f"profile_id={document_profile_id}, block_kind={block_kind}"
        )

    # 3. Загрузить prompt template
    pt_result = (
        sb.table("prompt_templates")
        .select("*")
        .eq("id", template_id)
        .eq("is_active", True)
        .execute()
    )
    if not pt_result.data:
        raise ValueError(f"Prompt template {template_id} не найден или не активен")

    pt = pt_result.data[0]
    variables = context.as_dict()

    # 4. Подстановка переменных
    system_prompt = _substitute_variables(pt["system_template"], variables)
    user_prompt = _substitute_variables(pt["user_template"], variables)

    # 5. Формирование snapshot
    snapshot = {
        "template_id": pt["id"],
        "template_key": pt["template_key"],
        "version": pt["version"],
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "parser_strategy": pt["parser_strategy"],
        "output_schema_json": pt.get("output_schema_json"),
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }

    _logger.info(
        "Prompt resolved",
        extra={
            "event": "prompt_resolved",
            "block_id": block_id,
            "template_id": pt["id"],
            "template_key": pt["template_key"],
            "version": pt["version"],
        },
    )

    return ResolvedPrompt(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        parser_strategy=pt["parser_strategy"],
        output_schema_json=pt.get("output_schema_json"),
        template_id=pt["id"],
        snapshot_json=snapshot,
    )
