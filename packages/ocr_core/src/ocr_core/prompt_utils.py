"""Shared утилиты для prompt templates — используются и API, и worker.

Извлечено из services/api/app/services/prompt_resolver.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


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
    template_version: int
    snapshot_json: dict[str, Any]


def substitute_variables(template: str, variables: dict[str, str]) -> str:
    """Безопасная подстановка {VARIABLE} в шаблон.

    Неизвестные переменные остаются как есть (не вызывают ошибку).
    """
    def replacer(match: re.Match) -> str:
        key = match.group(1)
        return variables.get(key, match.group(0))

    return re.sub(r"\{([A-Z_]+)\}", replacer, template)


def build_prompt_snapshot(
    template_row: dict[str, Any],
    system_prompt: str,
    user_prompt: str,
) -> dict[str, Any]:
    """Сформировать snapshot для recognition_attempts.prompt_snapshot_json."""
    return {
        "template_id": template_row["id"],
        "template_key": template_row["template_key"],
        "version": template_row["version"],
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "parser_strategy": template_row["parser_strategy"],
        "output_schema_json": template_row.get("output_schema_json"),
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }
