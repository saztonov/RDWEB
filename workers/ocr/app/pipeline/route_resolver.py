"""Route resolver — определяет source/model/prompt для блока.

Порядок приоритетов:
1. Block-level override (route_source_id, route_model_name)
2. profile_routes → primary_source_id, primary_model_name, fallback_chain_json
3. Block-level prompt override → prompt_template_id
4. profile_routes → default_prompt_template_id
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from supabase import Client

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FallbackEntry:
    """Элемент fallback chain."""

    source_id: str
    model_name: str
    fallback_no: int


@dataclass(frozen=True)
class RecognitionRoute:
    """Результат resolve — маршрут распознавания блока."""

    primary_source_id: str
    primary_model_name: str
    prompt_template_id: str
    fallback_chain: list[FallbackEntry] = field(default_factory=list)


class RouteResolver:
    """Resolve route для блока из profile_routes + block overrides."""

    def __init__(self, db: Client) -> None:
        self._db = db
        # Кэш profile_routes по (document_profile_id, block_kind)
        self._route_cache: dict[tuple[str, str], dict | None] = {}

    def resolve(self, block_data: dict, document_profile_id: str) -> RecognitionRoute:
        """Определить source/model/prompt для блока.

        Raises:
            ValueError: если route не найден.
        """
        block_kind = block_data["block_kind"]

        # Загрузить profile_route (с кэшем)
        route = self._get_profile_route(document_profile_id, block_kind)

        if not route:
            raise ValueError(
                f"Нет profile_route для profile={document_profile_id}, kind={block_kind}"
            )

        # Source/model: block override → route default
        source_id = block_data.get("route_source_id") or route["primary_source_id"]
        model_name = block_data.get("route_model_name") or route["primary_model_name"]

        if not source_id or not model_name:
            raise ValueError(
                f"Не задан source/model для блока {block_data['id']}: "
                f"source={source_id}, model={model_name}"
            )

        # Prompt template: block override → route default
        prompt_template_id = block_data.get("prompt_template_id") or route.get("default_prompt_template_id")

        if not prompt_template_id:
            raise ValueError(
                f"Не задан prompt_template для блока {block_data['id']}"
            )

        # Fallback chain
        fallback_chain = self._parse_fallback_chain(route.get("fallback_chain_json"))

        return RecognitionRoute(
            primary_source_id=source_id,
            primary_model_name=model_name,
            prompt_template_id=prompt_template_id,
            fallback_chain=fallback_chain,
        )

    def _get_profile_route(self, profile_id: str, block_kind: str) -> dict | None:
        """Загрузить profile_route с кэшем на время task."""
        key = (profile_id, block_kind)
        if key not in self._route_cache:
            result = (
                self._db.table("profile_routes")
                .select("*")
                .eq("document_profile_id", profile_id)
                .eq("block_kind", block_kind)
                .maybe_single()
                .execute()
            )
            self._route_cache[key] = result.data
        return self._route_cache[key]

    @staticmethod
    def _parse_fallback_chain(chain_json: list | None) -> list[FallbackEntry]:
        """Разобрать fallback_chain_json в список FallbackEntry."""
        if not chain_json:
            return []

        entries = []
        for idx, item in enumerate(chain_json, start=1):
            source_id = item.get("source_id", "")
            model_name = item.get("model_name", "")
            if source_id and model_name:
                entries.append(FallbackEntry(
                    source_id=source_id,
                    model_name=model_name,
                    fallback_no=idx,
                ))
        return entries
