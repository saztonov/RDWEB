"""Verifier — классификация OCR результата по коду качества.

Порядок проверок:
1. API error → API_ERROR
2. Пустой → EMPTY
3. Слишком короткий (для text) → TOO_SHORT
4. Stamp JSON → INVALID_STAMP_JSON
5. Image JSON → INVALID_IMAGE_JSON
6. Suspicious output → SUSPICIOUS_OUTPUT
7. Garbage → GARBAGE_OUTPUT
8. HTML fragment → PARSER_ERROR
9. → OK
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ocr_core.models import VerificationCode
from ocr_core.provider_types import RecognizeResult

from . import quality_checks as qc

logger = logging.getLogger(__name__)

# Error codes, которые не стоит ретраить
_NON_RETRIABLE_ERRORS = frozenset({
    "invalid_key", "no_credits", "forbidden",
    "context_exceeded", "invalid_coords",
})


@dataclass
class VerificationResult:
    """Результат verification OCR ответа."""

    code: VerificationCode
    is_retriable: bool
    details: str | None = None
    quality_flags: dict | None = None


class Verifier:
    """Верификатор OCR результатов.

    Проверяет RecognizeResult от OCR провайдера и возвращает
    VerificationResult с кодом, retriable-флагом и деталями.
    """

    def verify(
        self,
        response: RecognizeResult,
        block_kind: str,
        parser_strategy: str,
    ) -> VerificationResult:
        """Провести все проверки и вернуть первый провалившийся код или OK."""

        # 1. API / adapter error
        if response.is_error:
            non_retriable = response.error_code in _NON_RETRIABLE_ERRORS
            return VerificationResult(
                code=VerificationCode.API_ERROR,
                is_retriable=not non_retriable,
                details=f"{response.error_code}: {response.error_message}",
            )

        text = response.text

        # Очистить <think> теги
        text = qc.strip_think_tags(text)

        # 2. Пустой текст
        if qc.check_empty(text):
            return VerificationResult(
                code=VerificationCode.EMPTY,
                is_retriable=True,
                details="OCR вернул пустой результат",
            )

        # 3. Слишком короткий (только для text блоков)
        if block_kind == "text" and qc.check_too_short(text):
            return VerificationResult(
                code=VerificationCode.TOO_SHORT,
                is_retriable=True,
                details=f"Результат слишком короткий: {len(text.strip())} символов",
            )

        # 4. Stamp JSON validation
        if parser_strategy == "stamp_json":
            valid, error = qc.validate_stamp_json(text)
            if not valid:
                return VerificationResult(
                    code=VerificationCode.INVALID_STAMP_JSON,
                    is_retriable=True,
                    details=error,
                )

        # 5. Image JSON validation
        if parser_strategy == "image_json":
            valid, error = qc.validate_image_json(text)
            if not valid:
                return VerificationResult(
                    code=VerificationCode.INVALID_IMAGE_JSON,
                    is_retriable=True,
                    details=error,
                )

        # 6. Suspicious output
        suspicious, reason = qc.check_suspicious_output(text)
        if suspicious:
            return VerificationResult(
                code=VerificationCode.SUSPICIOUS_OUTPUT,
                is_retriable=True,
                details=reason,
            )

        # 7. Garbage output
        if qc.check_garbage(text):
            return VerificationResult(
                code=VerificationCode.GARBAGE_OUTPUT,
                is_retriable=True,
                details="Non-printable / repetitive content",
            )

        # 8. HTML fragment validation
        if parser_strategy == "html_fragment":
            valid, error = qc.validate_html_fragment(text)
            if not valid:
                return VerificationResult(
                    code=VerificationCode.PARSER_ERROR,
                    is_retriable=True,
                    details=error,
                )

        # 9. OK
        return VerificationResult(
            code=VerificationCode.OK,
            is_retriable=False,
        )
