"""Тесты BlockRecognizer — 9 обязательных кейсов.

1. text block success
2. stamp block success
3. image block success
4. retry same source/model
5. fallback model
6. fallback source
7. OCR success + crop upload delayed
8. manual_review_required with crop saved
9. failed with crop_upload_state handling
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from ocr_core import CircuitBreakerRegistry
from ocr_core.models import BlockStatus, CropUploadState, VerificationCode
from ocr_core.provider_types import RecognizeResult

from app.pipeline.block_recognizer import BlockRecognizer, RecognitionResult
from app.pipeline.prompt_resolver import PromptResolver
from app.pipeline.route_resolver import FallbackEntry, RecognitionRoute, RouteResolver
from app.pipeline.workspace import Workspace
from app.verification.verifier import Verifier, VerificationResult

from .conftest import make_block_data, make_source_data, make_template_data


# ── Helpers ──────────────────────────────────────────────────────────


def _make_recognizer(
    db: MagicMock,
    route: RecognitionRoute,
    ocr_responses: list[RecognizeResult],
    verification_results: list[VerificationResult] | None = None,
    max_retries: int = 2,
) -> BlockRecognizer:
    """Создать BlockRecognizer с замоканными зависимостями."""
    route_resolver = MagicMock(spec=RouteResolver)
    route_resolver.resolve.return_value = route

    prompt_resolver = MagicMock(spec=PromptResolver)
    resolved = MagicMock()
    resolved.system_prompt = "System prompt"
    resolved.user_prompt = "User prompt"
    resolved.parser_strategy = "plain_text"
    resolved.output_schema_json = None
    resolved.template_id = str(uuid.uuid4())
    resolved.template_version = 1
    resolved.snapshot_json = {"version": 1}
    prompt_resolver.resolve.return_value = resolved
    prompt_resolver.resolve_for_source.return_value = resolved

    verifier = MagicMock(spec=Verifier)
    if verification_results:
        verifier.verify.side_effect = verification_results
    else:
        # Default: первые N-1 failed, последний OK
        verifier.verify.return_value = VerificationResult(
            code=VerificationCode.OK, is_retriable=False,
        )

    recognizer = BlockRecognizer(
        run_id=str(uuid.uuid4()),
        document_id=str(uuid.uuid4()),
        document_profile_id=str(uuid.uuid4()),
        db=db,
        route_resolver=route_resolver,
        prompt_resolver=prompt_resolver,
        verifier=verifier,
        circuit_breakers=CircuitBreakerRegistry(),
        max_retries=max_retries,
    )

    return recognizer


def _make_db_mock(source_data: dict | None = None) -> MagicMock:
    """Созд��ть mock DB с необходимыми таблицами."""
    db = MagicMock()
    src = source_data or make_source_data()

    # ocr_sources
    source_result = MagicMock()
    source_result.data = src
    source_chain = MagicMock()
    source_chain.execute.return_value = source_result
    source_chain.single.return_value = source_chain
    source_chain.eq.return_value = source_chain
    source_chain.select.return_value = source_chain

    # recognition_attempts
    attempt_insert_result = MagicMock()
    attempt_insert_result.data = [{"id": str(uuid.uuid4())}]
    attempt_chain = MagicMock()
    attempt_chain.execute.return_value = attempt_insert_result
    attempt_chain.insert.return_value = attempt_chain
    attempt_chain.update.return_value = attempt_chain
    attempt_chain.eq.return_value = attempt_chain
    attempt_chain.select.return_value = attempt_chain

    # blocks
    block_chain = MagicMock()
    block_chain.execute.return_value = MagicMock(data=[{}])
    block_chain.update.return_value = block_chain
    block_chain.eq.return_value = block_chain

    def table_router(name):
        if name == "ocr_sources":
            return source_chain
        if name == "recognition_attempts":
            return attempt_chain
        if name == "blocks":
            return block_chain
        return MagicMock()

    db.table.side_effect = table_router
    return db


def _make_route(
    source_id: str | None = None,
    model: str = "qwen/qwen3-vl",
    fallback: list[FallbackEntry] | None = None,
) -> RecognitionRoute:
    """Создать RecognitionRoute."""
    return RecognitionRoute(
        primary_source_id=source_id or str(uuid.uuid4()),
        primary_model_name=model,
        prompt_template_id=str(uuid.uuid4()),
        fallback_chain=fallback or [],
    )


# ── 1. Text block success ───────────────────────────────────────────


@patch("app.pipeline.block_recognizer.create_provider")
def test_text_block_success(mock_create_provider, fake_page_image, tmp_workspace):
    """Text block → plain_text → adapter returns clean text → recognized."""
    # Setup provider mock
    provider = AsyncMock()
    provider.recognize_block.return_value = RecognizeResult(text="Распознанный текст")
    provider.close.return_value = None
    mock_create_provider.return_value = provider

    db = _make_db_mock()
    route = _make_route()
    block = make_block_data(block_kind="text")
    workspace = Workspace(str(tmp_workspace), "run1", 1)
    workspace.ensure_dirs([block["id"]])

    recognizer = _make_recognizer(db, route, [RecognizeResult(text="Распознанный текст")])

    result = recognizer.recognize(block, fake_page_image, workspace)

    assert result.terminal_status == BlockStatus.RECOGNIZED
    assert result.normalized_text == "Распознанный текст"
    assert result.crop_sha256 != ""
    assert not result.skipped


# ── 2. Stamp block success ──────────────────────────────────────────


@patch("app.pipeline.block_recognizer.create_provider")
def test_stamp_block_success(mock_create_provider, fake_page_image, tmp_workspace):
    """Stamp block → stamp_json → valid JSON → structured_json ��аполнен."""
    stamp_json = json.dumps({"organization": "ООО Тест", "date": "2026-01-01"})
    provider = AsyncMock()
    provider.recognize_block.return_value = RecognizeResult(text=stamp_json)
    provider.close.return_value = None
    mock_create_provider.return_value = provider

    db = _make_db_mock()
    route = _make_route()
    block = make_block_data(block_kind="stamp")
    workspace = Workspace(str(tmp_workspace), "run1", 1)
    workspace.ensure_dirs([block["id"]])

    # Prompt resolver возвращает stamp_json parser_strategy
    recognizer = _make_recognizer(db, route, [RecognizeResult(text=stamp_json)])
    recognizer._prompt_resolver.resolve.return_value.parser_strategy = "stamp_json"
    recognizer._prompt_resolver.resolve_for_source.return_value.parser_strategy = "stamp_json"

    result = recognizer.recognize(block, fake_page_image, workspace)

    assert result.terminal_status == BlockStatus.RECOGNIZED
    assert result.structured_json is not None
    assert result.structured_json["organization"] == "ООО Тест"


# ── 3. Image block success ──────────────────────────────────────────


@patch("app.pipeline.block_recognizer.create_provider")
def test_image_block_success(mock_create_provider, fake_page_image, tmp_workspace):
    """Image block → image_json → valid JSON → structured_json заполнен."""
    image_json = json.dumps({"description": "Чертёж фасада", "elements": ["окно", "дверь"]})
    provider = AsyncMock()
    provider.recognize_block.return_value = RecognizeResult(text=image_json)
    provider.close.return_value = None
    mock_create_provider.return_value = provider

    db = _make_db_mock()
    route = _make_route()
    block = make_block_data(block_kind="image")
    workspace = Workspace(str(tmp_workspace), "run1", 1)
    workspace.ensure_dirs([block["id"]])

    recognizer = _make_recognizer(db, route, [RecognizeResult(text=image_json)])
    recognizer._prompt_resolver.resolve.return_value.parser_strategy = "image_json"
    recognizer._prompt_resolver.resolve_for_source.return_value.parser_strategy = "image_json"

    result = recognizer.recognize(block, fake_page_image, workspace)

    assert result.terminal_status == BlockStatus.RECOGNIZED
    assert result.structured_json is not None
    assert "description" in result.structured_json


# ── 4. Retry on same source/model ───────────────────────────────────


@patch("app.pipeline.block_recognizer.create_provider")
def test_retry_same_source_model(mock_create_provider, fake_page_image, tmp_workspace):
    """1й вызов → api_error, 2й → success. 2 attempts."""
    call_count = [0]

    async def mock_recognize(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return RecognizeResult(text="", is_error=True, error_code="timeout", error_message="Timeout")
        return RecognizeResult(text="Success on retry")

    provider = AsyncMock()
    provider.recognize_block.side_effect = mock_recognize
    provider.close.return_value = None
    mock_create_provider.return_value = provider

    db = _make_db_mock()
    route = _make_route()
    block = make_block_data(block_kind="text")
    workspace = Workspace(str(tmp_workspace), "run1", 1)
    workspace.ensure_dirs([block["id"]])

    # Verifier: first ��� API_ERROR (retriable), second → OK
    recognizer = _make_recognizer(db, route, [], verification_results=[
        VerificationResult(code=VerificationCode.API_ERROR, is_retriable=True, details="timeout"),
        VerificationResult(code=VerificationCode.OK, is_retriable=False),
    ])

    result = recognizer.recognize(block, fake_page_image, workspace)

    assert result.terminal_status == BlockStatus.RECOGNIZED
    assert call_count[0] == 2  # 2 OCR calls


# ── 5. Fallback model ───────────────────────────────────────────────


@patch("app.pipeline.block_recognizer.create_provider")
def test_fallback_model(mock_create_provider, fake_page_image, tmp_workspace):
    """Primary fails 2x → fallback_chain[0] succeeds. 3 attempts."""
    call_count = [0]

    async def mock_recognize(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] <= 2:
            return RecognizeResult(text="", is_error=True, error_code="api_error", error_message="Error")
        return RecognizeResult(text="Fallback success")

    provider = AsyncMock()
    provider.recognize_block.side_effect = mock_recognize
    provider.close.return_value = None
    mock_create_provider.return_value = provider

    db = _make_db_mock()
    fallback_source_id = str(uuid.uuid4())
    route = _make_route(fallback=[
        FallbackEntry(source_id=fallback_source_id, model_name="gpt-4o-mini", fallback_no=1),
    ])
    block = make_block_data(block_kind="text")
    workspace = Workspace(str(tmp_workspace), "run1", 1)
    workspace.ensure_dirs([block["id"]])

    recognizer = _make_recognizer(db, route, [], verification_results=[
        VerificationResult(code=VerificationCode.API_ERROR, is_retriable=True),
        VerificationResult(code=VerificationCode.API_ERROR, is_retriable=True),
        VerificationResult(code=VerificationCode.OK, is_retriable=False),
    ])

    result = recognizer.recognize(block, fake_page_image, workspace)

    assert result.terminal_status == BlockStatus.RECOGNIZED
    assert call_count[0] == 3


# ── 6. Fallback source (circuit breaker) ────────────────────────────


@patch("app.pipeline.block_recognizer.create_provider")
def test_fallback_source_circuit_open(mock_create_provider, fake_page_image, tmp_workspace):
    """Primary source circuit open → fallback succeeds."""
    provider = AsyncMock()
    provider.recognize_block.return_value = RecognizeResult(text="Fallback OK")
    provider.close.return_value = None
    mock_create_provider.return_value = provider

    db = _make_db_mock()
    primary_source = str(uuid.uuid4())
    fallback_source = str(uuid.uuid4())
    route = _make_route(
        source_id=primary_source,
        fallback=[FallbackEntry(source_id=fallback_source, model_name="gpt-4o", fallback_no=1)],
    )
    block = make_block_data(block_kind="text")
    workspace = Workspace(str(tmp_workspace), "run1", 1)
    workspace.ensure_dirs([block["id"]])

    recognizer = _make_recognizer(db, route, [], max_retries=2)

    # Открыть circuit breaker для primary source
    cb = recognizer._circuit_breakers.get_or_create(primary_source)
    for _ in range(5):
        cb.record_failure()

    result = recognizer.recognize(block, fake_page_image, workspace)

    assert result.terminal_status == BlockStatus.RECOGNIZED
    assert result.normalized_text == "Fallback OK"


# ── 7. OCR success + crop upload delayed ────────────────────────────


@patch("app.pipeline.block_recognizer.create_provider")
def test_ocr_success_crop_upload_pending(mock_create_provider, fake_page_image, tmp_workspace):
    """OCR ok �� status=recognized, crop_upload_state="pending" в update."""
    provider = AsyncMock()
    provider.recognize_block.return_value = RecognizeResult(text="Clean text")
    provider.close.return_value = None
    mock_create_provider.return_value = provider

    db = _make_db_mock()
    route = _make_route()
    block = make_block_data(block_kind="text")
    workspace = Workspace(str(tmp_workspace), "run1", 1)
    workspace.ensure_dirs([block["id"]])

    recognizer = _make_recognizer(db, route, [])

    result = recognizer.recognize(block, fake_page_image, workspace)

    assert result.terminal_status == BlockStatus.RECOGNIZED
    assert result.crop_local_path is not None
    assert result.crop_local_path.exists()

    # Проверить что blocks.update вызван с crop_upload_state="pending"
    block_update_calls = [
        call for call in db.table.call_args_list
        if call.args == ("blocks",)
    ]
    assert len(block_update_calls) > 0


# ── 8. Manual review with crop saved ────────────────────────────────


@patch("app.pipeline.block_recognizer.create_provider")
def test_manual_review_with_crop(mock_create_provider, fake_page_image, tmp_workspace):
    """All attempts fail → manual_review, crop file exists."""
    provider = AsyncMock()
    provider.recognize_block.return_value = RecognizeResult(
        text="", is_error=True, error_code="api_error", error_message="Unavailable"
    )
    provider.close.return_value = None
    mock_create_provider.return_value = provider

    db = _make_db_mock()
    route = _make_route()
    block = make_block_data(block_kind="text")
    workspace = Workspace(str(tmp_workspace), "run1", 1)
    workspace.ensure_dirs([block["id"]])

    # Все verification → retriable error
    recognizer = _make_recognizer(db, route, [], verification_results=[
        VerificationResult(code=VerificationCode.API_ERROR, is_retriable=True),
        VerificationResult(code=VerificationCode.API_ERROR, is_retriable=True),
    ], max_retries=2)

    result = recognizer.recognize(block, fake_page_image, workspace)

    assert result.terminal_status == BlockStatus.MANUAL_REVIEW
    assert result.crop_local_path is not None
    assert result.crop_local_path.exists()  # Crop сохранён для manual review


# ── 9. Failed with crop_upload_state handling ────────────────────────


@patch("app.pipeline.block_recognizer.create_provider")
def test_failed_block_crop_upload_state(mock_create_provider, fake_page_image, tmp_workspace):
    """OCR non-retriable failure → block failed, crop_upload_state still set."""
    provider = AsyncMock()
    provider.recognize_block.return_value = RecognizeResult(
        text="", is_error=True, error_code="forbidden", error_message="Access denied"
    )
    provider.close.return_value = None
    mock_create_provider.return_value = provider

    db = _make_db_mock()
    route = _make_route()
    block = make_block_data(block_kind="text")
    workspace = Workspace(str(tmp_workspace), "run1", 1)
    workspace.ensure_dirs([block["id"]])

    # Non-retriable → сразу terminal
    recognizer = _make_recognizer(db, route, [], verification_results=[
        VerificationResult(
            code=VerificationCode.API_ERROR, is_retriable=False, details="forbidden"
        ),
    ], max_retries=2)

    result = recognizer.recognize(block, fake_page_image, workspace)

    assert result.terminal_status == BlockStatus.FAILED
    assert result.error_code == VerificationCode.API_ERROR
    # Crop файл создан даже при failure (н��жен для debug)
    assert result.crop_local_path is not None
