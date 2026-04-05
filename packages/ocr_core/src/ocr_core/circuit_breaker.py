"""Circuit Breaker для защиты от нестабильных OCR source-ов.

Адаптация из legacy_project/services/remote_ocr/server/circuit_breaker.py.
Три состояния: CLOSED → OPEN → HALF_OPEN.
Thread-safe, per-source, используется и в API, и в worker.
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Состояние circuit breaker-а."""

    CLOSED = "closed"  # Нормальная работа, запросы проходят
    OPEN = "open"  # Ошибок слишком много, запросы блокируются
    HALF_OPEN = "half_open"  # Пробный запрос для проверки восстановления


class CircuitOpenError(Exception):
    """Запрос заблокирован — circuit breaker открыт."""

    def __init__(self, service_name: str, retry_after: float) -> None:
        self.service_name = service_name
        self.retry_after = retry_after
        super().__init__(f"Circuit open for '{service_name}', retry after {retry_after:.0f}s")


class CircuitBreaker:
    """Circuit breaker с тремя состояниями.

    - CLOSED: запросы проходят, ошибки считаются
    - OPEN: запросы блокируются, ждём recovery_timeout
    - HALF_OPEN: пропускаем half_open_max_calls пробных запросов
      - success → CLOSED
      - failure → OPEN (сброс таймера)
    """

    def __init__(
        self,
        service_name: str,
        *,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self.service_name = service_name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._get_state()

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failure_count

    def _get_state(self) -> CircuitState:
        """Вычислить текущее состояние (вызывать под lock)."""
        if self._state == CircuitState.OPEN:
            # Автоматический переход OPEN → HALF_OPEN после recovery_timeout
            if time.monotonic() - self._last_failure_time >= self._recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info(
                    "Circuit breaker → HALF_OPEN для '%s' (recovery timeout истёк)",
                    self.service_name,
                )
        return self._state

    def allow_request(self) -> bool:
        """Проверить, можно ли выполнить запрос. True → можно."""
        with self._lock:
            state = self._get_state()

            if state == CircuitState.CLOSED:
                return True

            if state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self._half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False

            # OPEN
            return False

    def record_success(self) -> None:
        """Зафиксировать успешный запрос."""
        with self._lock:
            state = self._get_state()

            if state == CircuitState.HALF_OPEN:
                # Восстановление: HALF_OPEN → CLOSED
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._half_open_calls = 0
                logger.info("Circuit breaker → CLOSED для '%s' (восстановлен)", self.service_name)

            elif state == CircuitState.CLOSED:
                # Сбрасываем счётчик ошибок при успехе
                self._failure_count = 0

    def record_failure(self) -> None:
        """Зафиксировать ошибку."""
        with self._lock:
            state = self._get_state()

            if state == CircuitState.HALF_OPEN:
                # Пробный запрос упал — обратно в OPEN
                self._state = CircuitState.OPEN
                self._last_failure_time = time.monotonic()
                self._half_open_calls = 0
                logger.warning(
                    "Circuit breaker → OPEN для '%s' (half-open проба провалилась)",
                    self.service_name,
                )

            elif state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self._failure_threshold:
                    self._state = CircuitState.OPEN
                    self._last_failure_time = time.monotonic()
                    logger.warning(
                        "Circuit breaker → OPEN для '%s' (%d ошибок подряд)",
                        self.service_name,
                        self._failure_count,
                    )

    def get_retry_after(self) -> float:
        """Сколько секунд ждать до следующей попытки (для HTTP 503 Retry-After)."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - self._last_failure_time
                remaining = self._recovery_timeout - elapsed
                return max(0.0, remaining)
            return 0.0

    def reset(self) -> None:
        """Принудительный сброс — для тестов и admin override."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_calls = 0
            self._last_failure_time = 0.0
            logger.info("Circuit breaker сброшен для '%s'", self.service_name)

    def to_dict(self) -> dict[str, Any]:
        """Сериализация состояния для мониторинга."""
        with self._lock:
            state = self._get_state()
            return {
                "service_name": self.service_name,
                "state": state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self._failure_threshold,
                "recovery_timeout": self._recovery_timeout,
                "retry_after": self.get_retry_after() if state == CircuitState.OPEN else 0.0,
            }


class CircuitBreakerRegistry:
    """Реестр circuit breaker-ов по source_id.

    Per-process: у API и worker свои инстансы.
    """

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get_or_create(
        self,
        source_id: str,
        *,
        service_name: str = "",
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
    ) -> CircuitBreaker:
        """Получить или создать circuit breaker для source_id."""
        with self._lock:
            if source_id not in self._breakers:
                name = service_name or source_id
                self._breakers[source_id] = CircuitBreaker(
                    name,
                    failure_threshold=failure_threshold,
                    recovery_timeout=recovery_timeout,
                )
            return self._breakers[source_id]

    def get(self, source_id: str) -> CircuitBreaker | None:
        """Получить существующий breaker или None."""
        with self._lock:
            return self._breakers.get(source_id)

    def remove(self, source_id: str) -> None:
        """Удалить breaker (при деактивации source-а)."""
        with self._lock:
            self._breakers.pop(source_id, None)

    def all_states(self) -> dict[str, dict[str, Any]]:
        """Состояния всех breaker-ов — для мониторинга."""
        with self._lock:
            return {sid: cb.to_dict() for sid, cb in self._breakers.items()}
