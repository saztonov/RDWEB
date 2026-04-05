"""LM Studio OCR провайдер — единый адаптер для всех deployment_mode.

Адаптация из legacy:
- legacy_project/rd_core/ocr/chandra.py
- legacy_project/rd_core/ocr/_chandra_common.py
- legacy_project/services/remote_ocr/server/lmstudio_lifecycle.py

Один класс для:
- local/docker base_url
- remote ngrok/public base_url
- private URL

Различия определяются данными из ocr_sources и настройками timeout/retry.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import httpx

from ..provider import OcrProvider
from ..provider_types import (
    DeploymentMode,
    HealthResult,
    HealthStatus,
    ModelInfo,
    RecognizeResult,
    SourceConfig,
)

logger = logging.getLogger(__name__)

# Таймауты
_HEALTHCHECK_TIMEOUT = 10.0
_LIST_MODELS_TIMEOUT = 15.0
_MODEL_LOAD_TIMEOUT = 60.0

# App-level retry для нестабильных соединений (адаптация из legacy chandra.py)
_MAX_APP_RETRIES = 3
_APP_RETRY_DELAYS = [30, 60, 120]  # секунды между попытками

# Transient HTTP коды для retry (адаптация из legacy _chandra_common.py)
_TRANSIENT_CODES = {404, 429, 500, 502, 503, 504}

# Regex для очистки reasoning из ответа LM Studio (адаптация из legacy _chandra_common.py)
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[a-zA-Z][^>]*>")


class LmStudioProvider(OcrProvider):
    """LM Studio OCR провайдер.

    Единый адаптер для всех deployment_mode:
    - managed_api / docker / private_url: без auth, стандартный retry
    - remote_ngrok: HTTP Basic Auth, расширенный retry, ngrok headers
    """

    def __init__(self, config: SourceConfig) -> None:
        super().__init__(config)
        self._client: httpx.AsyncClient | None = None

    def _is_ngrok(self) -> bool:
        return self._config.deployment_mode == DeploymentMode.REMOTE_NGROK

    def _build_auth(self) -> httpx.BasicAuth | None:
        """HTTP Basic Auth — только для ngrok."""
        if not self._is_ngrok():
            return None
        user = self._config.credentials.get("auth_user", "")
        password = self._config.credentials.get("auth_pass", "")
        if user and password:
            return httpx.BasicAuth(user, password)
        return None

    def _get_extra_headers(self) -> dict[str, str]:
        """Дополнительные заголовки — ngrok-skip-browser-warning для ngrok."""
        if self._is_ngrok():
            return {"ngrok-skip-browser-warning": "true"}
        return {}

    def _build_transport(self) -> httpx.AsyncHTTPTransport:
        """Transport с retry. ngrok — более агрессивный retry."""
        if self._is_ngrok():
            return httpx.AsyncHTTPTransport(retries=2)
        return httpx.AsyncHTTPTransport(retries=1)

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-init httpx.AsyncClient."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                transport=self._build_transport(),
                auth=self._build_auth(),
                headers=self._get_extra_headers(),
                timeout=httpx.Timeout(self._config.timeout_sec, connect=10.0),
            )
        return self._client

    def _base_url_without_v1(self) -> str:
        """Base URL без /v1 суффикса — для LM Studio native API."""
        url = self._config.base_url.rstrip("/")
        if url.endswith("/v1"):
            return url[:-3]
        return url

    # ─── healthcheck ─────────────────────────────────────────────────────

    async def healthcheck(self) -> HealthResult:
        """GET /models — проверка доступности LM Studio."""
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
                status=HealthStatus.UNAVAILABLE,
                response_time_ms=elapsed_ms,
                details={"status_code": resp.status_code},
            )

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.warning("LM Studio healthcheck failed для '%s': %s", self._config.name, exc)
            return HealthResult(
                status=HealthStatus.UNAVAILABLE,
                response_time_ms=elapsed_ms,
                details={"error": str(exc)},
            )

    # ─── list_models ─────────────────────────────────────────────────────

    async def list_models(self) -> list[ModelInfo]:
        """GET /models — список загруженных моделей в LM Studio."""
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

                # LM Studio возвращает контекст в разных полях
                context_length = item.get("context_length") or item.get("max_context_length")

                models.append(
                    ModelInfo(
                        model_id=model_id,
                        model_name=model_id,
                        context_length=context_length,
                        supports_vision=True,  # Vision модели загружаются целенаправленно
                        extra={k: v for k, v in item.items() if k not in ("id", "object")},
                    )
                )

            logger.info(
                "LM Studio list_models для '%s': %d моделей",
                self._config.name,
                len(models),
            )
            return models

        except Exception as exc:
            logger.error("LM Studio list_models failed для '%s': %s", self._config.name, exc)
            raise

    # ─── recognize_block ──────────────────────────────────────��──────────

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
        """POST /chat/completions с app-level retry.

        Адаптация из legacy chandra.py: до 3 попыток с delays [30, 60, 120]s.
        Transient codes: {404, 429, 500, 502, 503, 504}.
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

        last_error: RecognizeResult | None = None

        for attempt in range(_MAX_APP_RETRIES + 1):
            # Задержка перед retry (не перед первой попыткой)
            if attempt > 0:
                delay = _APP_RETRY_DELAYS[min(attempt - 1, len(_APP_RETRY_DELAYS) - 1)]
                logger.info(
                    "LM Studio retry %d/%d для '%s' через %ds",
                    attempt,
                    _MAX_APP_RETRIES,
                    self._config.name,
                    delay,
                )
                await asyncio.sleep(delay)

            try:
                client = await self._get_client()
                resp = await client.post(
                    f"{self._config.base_url}/chat/completions",
                    json=payload,
                )

                if resp.status_code == 200:
                    return self._parse_response(resp)

                # Transient error — можно retry
                if resp.status_code in _TRANSIENT_CODES and attempt < _MAX_APP_RETRIES:
                    logger.warning(
                        "LM Studio transient error %d для '%s' (attempt %d)",
                        resp.status_code,
                        self._config.name,
                        attempt + 1,
                    )
                    last_error = RecognizeResult(
                        text="",
                        is_error=True,
                        error_code=f"http_{resp.status_code}",
                        error_message=f"HTTP {resp.status_code}: {resp.text[:300]}",
                    )
                    continue

                # Не-transient ошибка — сразу возвращаем
                return RecognizeResult(
                    text="",
                    is_error=True,
                    error_code=f"http_{resp.status_code}",
                    error_message=f"HTTP {resp.status_code}: {resp.text[:500]}",
                )

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt < _MAX_APP_RETRIES:
                    logger.warning(
                        "LM Studio connection error для '%s' (attempt %d): %s",
                        self._config.name,
                        attempt + 1,
                        exc,
                    )
                    last_error = RecognizeResult(
                        text="",
                        is_error=True,
                        error_code="connection_error",
                        error_message=str(exc),
                    )
                    continue

                return RecognizeResult(
                    text="",
                    is_error=True,
                    error_code="timeout" if isinstance(exc, httpx.TimeoutException) else "connection_error",
                    error_message=str(exc),
                )

            except Exception as exc:
                logger.error(
                    "LM Studio recognize failed для '%s': %s",
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

        # Все retry исчерпаны
        return last_error or RecognizeResult(
            text="",
            is_error=True,
            error_code="max_retries",
            error_message=f"Все {_MAX_APP_RETRIES} попытки исчерпаны",
        )

    # ─── LM Studio native API: load/unload ──────────────────────────���────

    async def load_model(self, model_id: str, load_config: dict[str, Any] | None = None) -> bool:
        """POST /api/v1/models/load — загрузка модели в LM Studio.

        Адаптация из legacy lmstudio_lifecycle.py.
        """
        base = self._base_url_without_v1()
        payload: dict[str, Any] = {"model": model_id}
        if load_config:
            payload.update(load_config)

        try:
            client = await self._get_client()
            resp = await client.post(
                f"{base}/api/v1/models/load",
                json=payload,
                timeout=_MODEL_LOAD_TIMEOUT,
            )
            if resp.status_code == 200:
                logger.info("LM Studio модель '%s' загружена на '%s'", model_id, self._config.name)
                return True

            logger.warning(
                "LM Studio load_model %d для '%s': %s",
                resp.status_code,
                self._config.name,
                resp.text[:300],
            )
            return False

        except Exception as exc:
            logger.warning("LM Studio load_model failed для '%s': %s", self._config.name, exc)
            return False

    async def unload_model(self, model_id: str) -> bool:
        """POST /api/v1/models/unload — выгрузка модели из LM Studio."""
        base = self._base_url_without_v1()

        try:
            client = await self._get_client()
            resp = await client.post(
                f"{base}/api/v1/models/unload",
                json={"model": model_id},
                timeout=30.0,
            )
            if resp.status_code == 200:
                logger.info("LM Studio модель '%s' выгружена с '%s'", model_id, self._config.name)
                return True

            logger.warning(
                "LM Studio unload_model %d для '%s': %s",
                resp.status_code,
                self._config.name,
                resp.text[:300],
            )
            return False

        except Exception as exc:
            logger.warning("LM Studio unload_model failed для '%s': %s", self._config.name, exc)
            return False

    # ─── Приватные методы ─────────────────────────────────────────────────

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
        """Формирование payload для LM Studio chat/completions.

        Адаптация из legacy _chandra_common.build_payload().
        """
        messages: list[dict[str, Any]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

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
            "top_p": 0.95,
            "top_k": 40,
            "repetition_penalty": 1.1,
            "min_p": 0.05,
        }

        if response_format:
            payload["response_format"] = response_format

        return payload

    def _parse_response(self, resp: httpx.Response) -> RecognizeResult:
        """Парсинг ответа LM Studio.

        Адаптация из legacy _chandra_common._normalize_chandra_response().
        Обрабатывает: structured output, content, reasoning_content.
        Очищает <think> теги и reasoning-прозу.
        """
        try:
            data = resp.json()
        except Exception:
            return RecognizeResult(
                text=resp.text,
                is_error=True,
                error_code="json_parse_error",
                error_message="Не удалось распарсить JSON ответ LM Studio",
            )

        choices = data.get("choices", [])
        if not choices:
            return RecognizeResult(
                text="",
                is_error=True,
                error_code="empty_choices",
                error_message="Ответ не содержит choices",
            )

        message = choices[0].get("message", {})
        usage = data.get("usage", {})

        # Приоритет 1: structured output (JSON с ocr_html ключом)
        # Приоритет 2: content
        # Приоритет 3: reasoning_content (для reasoning-моделей LM Studio)
        content = message.get("content", "")
        if not content:
            content = message.get("reasoning_content", "")

        if isinstance(content, list):
            # Мультимодальный ответ — собираем текст
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(part.get("text", ""))
                elif isinstance(part, str):
                    parts.append(part)
            content = "\n".join(parts)

        if not content:
            return RecognizeResult(
                text="",
                is_error=True,
                error_code="empty_content",
                error_message="Ответ LM Studio содержит пустой content",
                usage=usage,
            )

        # Очистка: удаление <think>...</think> тегов
        content = _strip_think_tags(content)

        return RecognizeResult(text=content, usage=usage)

    async def close(self) -> None:
        """Закрыть httpx client."""
        if self._client:
            await self._client.aclose()
            self._client = None


def _strip_think_tags(text: str) -> str:
    """Удалить <think>...</think> теги из ответа.

    Адаптация из legacy _chandra_common.strip_think_tags().
    """
    cleaned = _THINK_TAG_RE.sub("", text).strip()
    return cleaned if cleaned else text
