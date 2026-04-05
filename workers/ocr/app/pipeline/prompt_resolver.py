"""Prompt resolver для worker — resolve prompt template из БД.

Использует shared логику из ocr_core.prompt_utils.
DB client — worker's infra.db вместо API's get_supabase().
"""

from __future__ import annotations

import logging

from ocr_core.prompt_utils import (
    PromptContext,
    ResolvedPrompt,
    build_prompt_snapshot,
    substitute_variables,
)
from supabase import Client

logger = logging.getLogger(__name__)


class PromptResolver:
    """Resolve prompt template для OCR pipeline."""

    def __init__(self, db: Client) -> None:
        self._db = db
        # Кэш prompt templates по id
        self._cache: dict[str, dict] = {}

    def resolve(
        self,
        prompt_template_id: str,
        context: PromptContext,
    ) -> ResolvedPrompt:
        """Загрузить и подставить переменные в prompt template.

        Args:
            prompt_template_id: UUID prompt template из route.
            context: Переменные для подстановки.

        Returns:
            ResolvedPrompt с готовыми промптами и snapshot.

        Raises:
            ValueError: если template не найден или не активен.
        """
        pt = self._load_template(prompt_template_id)

        variables = context.as_dict()
        system_prompt = substitute_variables(pt["system_template"], variables)
        user_prompt = substitute_variables(pt["user_template"], variables)

        snapshot = build_prompt_snapshot(pt, system_prompt, user_prompt)

        return ResolvedPrompt(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            parser_strategy=pt["parser_strategy"],
            output_schema_json=pt.get("output_schema_json"),
            template_id=pt["id"],
            template_version=pt["version"],
            snapshot_json=snapshot,
        )

    def _load_template(self, template_id: str) -> dict:
        """Загрузить template из БД (с кэшем на время task)."""
        if template_id not in self._cache:
            result = (
                self._db.table("prompt_templates")
                .select("*")
                .eq("id", template_id)
                .eq("is_active", True)
                .maybe_single()
                .execute()
            )
            if not result.data:
                raise ValueError(f"Prompt template {template_id} не найден или не активен")
            self._cache[template_id] = result.data

        return self._cache[template_id]

    def resolve_for_source(
        self,
        block_data: dict,
        document_profile_id: str,
        source_id: str,
        source_type: str,
        model_name: str,
        context: PromptContext,
    ) -> ResolvedPrompt:
        """Resolve prompt для конкретного source/model.

        Ищет prompt template, соответствующий source_type и model_name.
        Если block override задан — использует его.
        """
        # Block-level override имеет приоритет
        template_id = block_data.get("prompt_template_id")

        if not template_id:
            # Ищем route default
            route_result = (
                self._db.table("profile_routes")
                .select("default_prompt_template_id")
                .eq("document_profile_id", document_profile_id)
                .eq("block_kind", block_data["block_kind"])
                .maybe_single()
                .execute()
            )
            if route_result.data:
                template_id = route_result.data.get("default_prompt_template_id")

        if not template_id:
            raise ValueError(
                f"Нет prompt template для блока {block_data['id']}, "
                f"source_type={source_type}, model={model_name}"
            )

        # Обогатить контекст source/model
        enriched = PromptContext(
            doc_name=context.doc_name,
            page_num=context.page_num,
            block_id=context.block_id,
            block_kind=context.block_kind,
            operator_hint=context.operator_hint,
            pdf_text=context.pdf_text,
            source_name=source_type,
            model_name=model_name,
        )

        return self.resolve(template_id, enriched)
