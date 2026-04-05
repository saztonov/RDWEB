"""Тесты Verifier — все verification codes."""

from __future__ import annotations

import pytest

from ocr_core.models import VerificationCode
from ocr_core.provider_types import RecognizeResult

from app.verification.verifier import Verifier


@pytest.fixture
def verifier() -> Verifier:
    return Verifier()


def test_ok_text(verifier):
    """Нормальный текст → OK."""
    resp = RecognizeResult(text="Это нормальный OCR результат.")
    result = verifier.verify(resp, "text", "plain_text")
    assert result.code == VerificationCode.OK


def test_empty(verifier):
    """Пустой текст → EMPTY."""
    resp = RecognizeResult(text="")
    result = verifier.verify(resp, "text", "plain_text")
    assert result.code == VerificationCode.EMPTY
    assert result.is_retriable


def test_api_error_retriable(verifier):
    """Retriable API error → API_ERROR + retriable."""
    resp = RecognizeResult(text="", is_error=True, error_code="timeout", error_message="Timeout")
    result = verifier.verify(resp, "text", "plain_text")
    assert result.code == VerificationCode.API_ERROR
    assert result.is_retriable


def test_api_error_non_retriable(verifier):
    """Non-retriable API error → API_ERROR + not retriable."""
    resp = RecognizeResult(text="", is_error=True, error_code="forbidden", error_message="Access denied")
    result = verifier.verify(resp, "text", "plain_text")
    assert result.code == VerificationCode.API_ERROR
    assert not result.is_retriable


def test_too_short_text(verifier):
    """Слишком короткий текст → TOO_SHORT (только для text)."""
    resp = RecognizeResult(text="ab")
    result = verifier.verify(resp, "text", "plain_text")
    assert result.code == VerificationCode.TOO_SHORT
    assert result.is_retriable


def test_too_short_not_for_stamp(verifier):
    """Короткий текст для stamp → не TOO_SHORT (stamp может быть коротким)."""
    resp = RecognizeResult(text='{"a":1}')
    result = verifier.verify(resp, "stamp", "stamp_json")
    assert result.code == VerificationCode.OK


def test_invalid_stamp_json(verifier):
    """Невалидный JSON для stamp → INVALID_STAMP_JSON."""
    resp = RecognizeResult(text="not json at all")
    result = verifier.verify(resp, "stamp", "stamp_json")
    assert result.code == VerificationCode.INVALID_STAMP_JSON
    assert result.is_retriable


def test_valid_stamp_json(verifier):
    """Валидный JSON для stamp → OK."""
    resp = RecognizeResult(text='{"organization": "ООО Тест", "date": "2026-01-01"}')
    result = verifier.verify(resp, "stamp", "stamp_json")
    assert result.code == VerificationCode.OK


def test_invalid_image_json(verifier):
    """Невалидный JSON для image → INVALID_IMAGE_JSON."""
    resp = RecognizeResult(text="{broken json")
    result = verifier.verify(resp, "image", "image_json")
    assert result.code == VerificationCode.INVALID_IMAGE_JSON


def test_suspicious_bbox_dump(verifier):
    """JSON bbox dump → SUSPICIOUS_OUTPUT."""
    text = '{"bbox": [10, 20, 30, 40]} {"bbox": [50, 60, 70, 80]} {"bbox": [1,2,3,4]} {"bbox": [5,6,7,8]}'
    resp = RecognizeResult(text=text)
    result = verifier.verify(resp, "text", "plain_text")
    assert result.code == VerificationCode.SUSPICIOUS_OUTPUT


def test_garbage_repetitive(verifier):
    """Повторяющийся мусор → GARBAGE_OUTPUT."""
    resp = RecognizeResult(text="abc" * 100)
    result = verifier.verify(resp, "text", "plain_text")
    assert result.code == VerificationCode.GARBAGE_OUTPUT


def test_think_tags_stripped(verifier):
    """<think> теги удаляются перед проверкой."""
    resp = RecognizeResult(text="<think>reasoning here</think>Actual OCR content that is valid.")
    result = verifier.verify(resp, "text", "plain_text")
    assert result.code == VerificationCode.OK
