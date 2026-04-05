"""OpenRouter OCR провайдер.

Адаптация из legacy:
- legacy_project/rd_core/ocr/openrouter.py
- legacy_project/rd_core/ocr/_openrouter_common.py
- legacy_project/rd_core/ocr/http_utils.py

Ключевые отличия от legacy:
- async httpx вместо sync requests
- промпты приходят извне (не хардкодятся)
- без кэша провайдеров по цене (не нужен для MVP)
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from ..provider import OcrProvider
from ..provider_types import HealthResult, HealthStatus, ModelInfo, RecognizeResult, SourceConfig

logger = logging.getLogger(__name__)

# Таймауты для разных операций
_HEALTHCHECK_TIMEOUT = 10.0
_LIST_MODELS_TIMEOUT = 30.0


class OpenRouterProvider(OcrProvider):
    """OpenRouter OCR провайдер (httpx async).

    API: OpenAI-compatible endpoints.
    Auth: Bearer token из credentials["api_key"].
    """

    def __init__(self, config: SourceConfig) -> None:
        super().__init__(config)
        self._client: httpx.AsyncClient | None = None

    def _get_api_key(self) -> str:
        key = self._config.credentials.get("api_key", "")
        if not key:
            raise ValueError(f"OpenRouter source '{self._config.name}': api_key не задан в credentials")
        return key

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_api_key()}",
            "Content-Type": "application/json",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-init httpx.AsyncClient с retry transport."""
        if self._client is None:
            transport = httpx.AsyncHTTPTransport(
                retries=3,
            )
            self._client = httpx.AsyncClient(
                transport=transport,
                headers=self._get_headers(),
                timeout=httpx.Timeout(self._config.timeout_sec, connect=10.0),
            )
        return self._client

    async def healthcheck(self) -> HealthResult:
        """GET /models — проверка доступности API."""
        start = time.monotonic()
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{self._config.base_url}/models",
                timeout=_HEALTHCHECK_TIMEOUT,
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)

            if resp.status_code == 200:
                data = resp.json()
                model_count = len(data.get("data", []))
                return HealthResult(
                    status=HealthStatus.HEALTHY,
                    response_time_ms=elapsed_ms,
                    details={"model_count": model_count},
                )

            return HealthResult(
                status=HealthStatus.DEGRADED if resp.status_code < 500 else HealthStatus.UNAVAILABLE,
                response_time_ms=elapsed_ms,
                details={"status_code": resp.status_code, "body": resp.text[:500]},
            )

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.warning("OpenRouter healthcheck failed для '%s': %s", self._config.name, exc)
            return HealthResult(
                status=HealthStatus.UNAVAILABLE,
                response_time_ms=elapsed_ms,
                details={"error": str(exc)},
            )

    async def list_models(self) -> list[ModelInfo]:
        """GET /models — список моделей с фильтрацией по vision support."""
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{self._config.base_url}/models",
                timeout=_LIST_MODELS_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            models: list[ModelInfo] = []
            for item in data.get("data", []):
                model_id = item.get("id", "")
                if not model_id:
                    continue

                # Определяем поддержку vision из architecture.modality
                arch = item.get("architecture", {})
                modality = arch.get("modality", "")
                supports_vision = "image" in modality.lower() if modality else False

                context_length = item.get("context_length")

                # Дополнительные данные
                extra: dict[str, Any] = {}
                pricing = item.get("pricing", {})
                if pricing:
                    extra["pricing"] = pricing
                if arch:
                    extra["architecture"] = arch

                models.append(
                    ModelInfo(
                        model_id=model_id,
                        model_name=item.get("name", model_id),
                        context_length=context_length,
                        supports_vision=supports_vision,
                        extra=extra,
                    )
                )

            logger.info(
                "OpenRouter list_models для '%s': %d моделей (vision: %d)",
                self._config.name,
                len(models),
                sum(1 for m in models if m.supports_vision),
            )
            return models

        except Exception as exc:
            logger.error("OpenRouter list_models failed для '%s': %s", self._config.name, exc)
            raise

    async def recognize_block(
        self,
        image_b64: str,
        system_prompt: str,
        user_prompt: str,
        model_id: str,
        *,
        max_tokens: int = 16384,
        temperature: float = 0.1,
        response_format: dict[str, Any] | None = None,
    ) -> RecognizeResult:
        """POST /chat/completions — распознавание блока.

        Payload адаптирован из legacy _openrouter_common.build_payload().
        Error mapping: 401→invalid_key, 402→no_credits, 403→forbidden, 429→rate_limit.
        """
        payload = self._build_payload(
            image_b64=image_b64,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_id=model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format=response_format,
        )

        try:
            client = await self._get_client()
            resp = await client.post(
                f"{self._config.base_url}/chat/completions",
                json=payload,
            )
            return self._parse_response(resp)

        except httpx.TimeoutException:
            logger.warning(
                "OpenRouter recognize timeout для '%s', model=%s",
                self._config.name,
                model_id,
            )
            return RecognizeResult(
                text="",
                is_error=True,
                error_code="timeout",
                error_message=f"Timeout ({self._config.timeout_sec}s)",
            )

        except Exception as exc:
            logger.error(
                "OpenRouter recognize failed для '%s': %s",
                self._config.name,
                exc,
                exc_info=True,
            )
            return RecognizeResult(
                text="",
                is_error=True,
                error_code="request_error",
                error_message=str(exc),
            )

    def _build_payload(
        self,
        *,
        image_b64: str,
        system_prompt: str,
        user_prompt: str,
        model_id: str,
        max_tokens: int,
        temperature: float,
        response_format: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Формирование payload для chat/completions.

        Адаптация из legacy _openrouter_common.build_payload().
        """
        messages: list[dict[str, Any]] = []

        # System message
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # User message: image + text
        user_content: list[dict[str, Any]] = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_b64}"},
            },
        ]
        if user_prompt:
            user_content.append({"type": "text", "text": user_prompt})

        messages.append({"role": "user", "content": user_content})

        payload: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": 0.9,
        }

        if response_format:
            payload["response_format"] = response_format

        return payload

    def _parse_response(self, resp: httpx.Response) -> RecognizeResult:
        """Парсинг ответа. Адаптация из legacy _openrouter_common.parse_response()."""
        # Маппинг HTTP ошибок
        error_map: dict[int, tuple[str, str]] = {
            401: ("invalid_key", "Неверный API ключ OpenRouter"),
            402: ("no_credits", "Недостаточно кредитов OpenRouter"),
            403: ("forbidden", "Доступ запрещён — проверьте ключ и баланс"),
            429: ("rate_limit", "Превышен лимит запросов OpenRouter"),
        }

        if resp.status_code in error_map:
            code, msg = error_map[resp.status_code]
            return RecognizeResult(text="", is_error=True, error_code=code, error_message=msg)

        if resp.status_code != 200:
            body = resp.text[:500]
            return RecognizeResult(
                text="",
                is_error=True,
                error_code=f"http_{resp.status_code}",
                error_message=f"HTTP {resp.status_code}: {body}",
            )

        # Парсинг успешного ответа
        try:
            data = resp.json()
        except Exception:
            return RecognizeResult(
                text=resp.text,
                is_error=True,
                error_code="json_parse_error",
                error_message="Не удалось распарсить JSON ответ",
            )

        # Извлечь текст из choices[0].message.content
        choices = data.get("choices", [])
        if not choices:
            return RecognizeResult(
                text="",
                is_error=True,
                error_code="empty_choices",
                error_message="Ответ не содержит choices",
            )

        content = choices[0].get("message", {}).get("content", "")

        # Usage для мониторинга
        usage = data.get("usage", {})

        if not content:
            return RecognizeResult(
                text="",
                is_error=True,
                error_code="empty_content",
                error_message="Ответ содержит пустой content",
                usage=usage,
            )

        return RecognizeResult(text=content, usage=usage)

    async def close(self) -> None:
        """Закрыть httpx client."""
        if self._client:
            await self._client.aclose()
            self._client = None
