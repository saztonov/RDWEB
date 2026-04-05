"""Block recognizer — полный цикл OCR одного блока.

Flow:
1. Crop из page_image → save → SHA256
2. Build signature → idempotency check
3. Resolve route → build attempts chain
4. OCR loop: adapter call → verify → retry/fallback
5. Write attempt + update block → dispatch crop upload
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image
from supabase import Client

from ocr_core import CircuitBreakerRegistry, create_provider
from ocr_core.cropper import crop_block_image
from ocr_core.models import AttemptStatus, BlockStatus, CropUploadState, VerificationCode
from ocr_core.prompt_utils import PromptContext
from ocr_core.provider_types import DeploymentMode, RecognizeResult, SourceConfig, SourceType

from ..verification.verifier import Verifier, VerificationResult
from .prompt_resolver import PromptResolver
from .route_resolver import FallbackEntry, RecognitionRoute, RouteResolver
from .signature import build_pipeline_signature, compute_crop_sha256, is_signature_match
from .workspace import Workspace

logger = logging.getLogger(__name__)


@dataclass
class RecognitionResult:
    """Результат распознавания одного блока."""

    block_id: str
    terminal_status: str  # recognized | manual_review | failed
    attempt_id: str | None = None
    normalized_text: str | None = None
    structured_json: dict | None = None
    render_html: str | None = None
    quality_flags: dict | None = None
    error_code: str | None = None
    crop_sha256: str = ""
    crop_local_path: Path | None = None
    skipped: bool = False  # True если idempotent skip


@dataclass
class _AttemptStep:
    """Один шаг в attempts chain."""

    source_id: str
    model_name: str
    attempt_no: int
    fallback_no: int


class BlockRecognizer:
    """OCR одного блока: crop → call → verify → write."""

    def __init__(
        self,
        run_id: str,
        document_id: str,
        document_profile_id: str,
        db: Client,
        route_resolver: RouteResolver,
        prompt_resolver: PromptResolver,
        verifier: Verifier,
        circuit_breakers: CircuitBreakerRegistry,
        max_retries: int = 2,
    ) -> None:
        self._run_id = run_id
        self._document_id = document_id
        self._document_profile_id = document_profile_id
        self._db = db
        self._route_resolver = route_resolver
        self._prompt_resolver = prompt_resolver
        self._verifier = verifier
        self._circuit_breakers = circuit_breakers
        self._max_retries = max_retries
        # Кэш source configs
        self._source_configs: dict[str, SourceConfig] = {}

    def recognize(
        self,
        block_data: dict,
        page_image: Image.Image,
        workspace: Workspace,
        doc_name: str = "",
    ) -> RecognitionResult:
        """Полный цикл распознавания одного блока."""
        block_id = block_data["id"]
        block_kind = block_data["block_kind"]

        # 1. Crop
        crop_img = crop_block_image(
            page_image,
            block_data["bbox_json"],
            block_data.get("polygon_json"),
            block_data.get("shape_type", "rect"),
        )

        # 2. Save crop + SHA256
        crop_path = workspace.crop_path(block_id)
        crop_bytes = _image_to_png_bytes(crop_img)
        crop_path.write_bytes(crop_bytes)
        crop_sha = compute_crop_sha256(crop_bytes)

        # 3. Route resolution
        try:
            route = self._route_resolver.resolve(block_data, self._document_profile_id)
        except ValueError as exc:
            logger.error("Route resolve failed для block=%s: %s", block_id, exc)
            return RecognitionResult(
                block_id=block_id,
                terminal_status=BlockStatus.FAILED,
                error_code="route_resolve_error",
                crop_sha256=crop_sha,
                crop_local_path=crop_path,
            )

        # 4. Signature + idempotency
        # Для idempotency нужен template version — загрузим
        try:
            resolved = self._prompt_resolver.resolve(
                route.prompt_template_id,
                PromptContext(block_kind=block_kind),
            )
            template_version = resolved.template_version
        except ValueError:
            template_version = 0

        signature = build_pipeline_signature(
            geometry_rev=block_data["geometry_rev"],
            block_kind=block_kind,
            source_id=route.primary_source_id,
            model_name=route.primary_model_name,
            prompt_template_id=route.prompt_template_id,
            prompt_template_version=template_version,
            parser_version="1",
            crop_sha256=crop_sha,
        )

        if is_signature_match(block_data, signature):
            logger.info("Block %s skipped — signature match (idempotent)", block_id)
            return RecognitionResult(
                block_id=block_id,
                terminal_status=block_data["current_status"],
                crop_sha256=crop_sha,
                crop_local_path=crop_path,
                skipped=True,
            )

        # 5. Build attempts chain
        steps = self._build_attempts_chain(route)

        # 6. OCR loop
        image_b64 = base64.b64encode(crop_bytes).decode("ascii")
        success_result: RecognitionResult | None = None
        last_error_code: str | None = None
        had_non_retriable: bool = False

        context = PromptContext(
            doc_name=doc_name,
            page_num=block_data["page_number"],
            block_id=block_id,
            block_kind=block_kind,
        )

        for step in steps:
            # Circuit breaker check
            cb = self._circuit_breakers.get_or_create(step.source_id)
            if not cb.allow_request():
                logger.info(
                    "Circuit open для source=%s, skipping step (block=%s)",
                    step.source_id, block_id,
                )
                self._write_attempt(
                    block_data, step, route.prompt_template_id,
                    AttemptStatus.SKIPPED, None, "circuit_open", "Circuit breaker open", {},
                )
                continue

            # Resolve prompt для этого source/model
            try:
                source_config = self._get_source_config(step.source_id)
                resolved = self._prompt_resolver.resolve_for_source(
                    block_data, self._document_profile_id,
                    step.source_id, source_config.source_type,
                    step.model_name, context,
                )
            except ValueError as exc:
                logger.error(
                    "Prompt resolve failed: block=%s, source=%s: %s",
                    block_id, step.source_id, exc,
                )
                self._write_attempt(
                    block_data, step, route.prompt_template_id,
                    AttemptStatus.FAILED, None, "prompt_resolve_error", str(exc), {},
                )
                continue

            # OCR call
            attempt_id, ocr_result = self._call_ocr(
                block_data, step, route.prompt_template_id,
                resolved, image_b64, source_config,
            )

            # Verify
            vr = self._verifier.verify(ocr_result, block_kind, resolved.parser_strategy)

            if vr.code == VerificationCode.OK:
                # Success!
                text = ocr_result.text
                structured = None
                if resolved.parser_strategy in ("stamp_json", "image_json"):
                    import json
                    try:
                        structured = json.loads(text)
                    except Exception:
                        structured = {"raw": text}

                self._update_attempt(attempt_id, AttemptStatus.SUCCESS, vr)
                cb.record_success()

                success_result = RecognitionResult(
                    block_id=block_id,
                    terminal_status=BlockStatus.RECOGNIZED,
                    attempt_id=attempt_id,
                    normalized_text=text,
                    structured_json=structured,
                    render_html=text if resolved.parser_strategy == "html_fragment" else None,
                    quality_flags=vr.quality_flags,
                    crop_sha256=crop_sha,
                    crop_local_path=crop_path,
                )
                break
            else:
                # Failed verification
                self._update_attempt(attempt_id, AttemptStatus.FAILED, vr)
                last_error_code = vr.code.value
                if vr.is_retriable:
                    cb.record_failure()
                    continue
                else:
                    # Non-retriable — прекратить
                    had_non_retriable = True
                    cb.record_failure()
                    break

        if success_result:
            # Обновить блок в БД
            self._update_block_recognized(block_data, success_result, signature)
            return success_result

        # Все attempts исчерпаны
        # Non-retriable error → failed, retriable exhausted → manual_review
        if had_non_retriable:
            terminal = BlockStatus.FAILED
        elif last_error_code:
            terminal = BlockStatus.MANUAL_REVIEW
        else:
            terminal = BlockStatus.FAILED
        result = RecognitionResult(
            block_id=block_id,
            terminal_status=terminal,
            error_code=last_error_code or "all_attempts_exhausted",
            crop_sha256=crop_sha,
            crop_local_path=crop_path,
        )
        self._update_block_terminal(block_data, result, signature)
        return result

    # ── Приватные методы ─────────────────────────────────────────────

    def _build_attempts_chain(self, route: RecognitionRoute) -> list[_AttemptStep]:
        """Построить цепочку попыток: primary × retries + fallback chain."""
        steps: list[_AttemptStep] = []

        # Primary: attempt_no 1..max_retries
        for attempt_no in range(1, self._max_retries + 1):
            steps.append(_AttemptStep(
                source_id=route.primary_source_id,
                model_name=route.primary_model_name,
                attempt_no=attempt_no,
                fallback_no=0,
            ))

        # Fallback entries
        for entry in route.fallback_chain:
            steps.append(_AttemptStep(
                source_id=entry.source_id,
                model_name=entry.model_name,
                attempt_no=1,
                fallback_no=entry.fallback_no,
            ))

        return steps

    def _get_source_config(self, source_id: str) -> SourceConfig:
        """Загрузить SourceConfig из БД (с кэшем)."""
        if source_id not in self._source_configs:
            result = (
                self._db.table("ocr_sources")
                .select("*")
                .eq("id", source_id)
                .single()
                .execute()
            )
            row = result.data
            self._source_configs[source_id] = SourceConfig(
                id=row["id"],
                source_type=SourceType(row["source_type"]),
                name=row["name"],
                base_url=row["base_url"],
                deployment_mode=DeploymentMode(row["deployment_mode"]),
                credentials=row.get("credentials_json") or {},
                concurrency_limit=row.get("concurrency_limit", 4),
                timeout_sec=row.get("timeout_sec", 120),
                capabilities=row.get("capabilities_json") or {},
            )
        return self._source_configs[source_id]

    def _call_ocr(
        self,
        block_data: dict,
        step: _AttemptStep,
        prompt_template_id: str,
        resolved: Any,
        image_b64: str,
        source_config: SourceConfig,
    ) -> tuple[str, RecognizeResult]:
        """Вызвать OCR провайдер и записать attempt."""
        now = datetime.now(timezone.utc).isoformat()

        # INSERT attempt (status=running)
        attempt_data = {
            "run_id": self._run_id,
            "block_id": block_data["id"],
            "geometry_rev": block_data["geometry_rev"],
            "source_id": step.source_id,
            "model_name": step.model_name,
            "prompt_template_id": prompt_template_id,
            "prompt_snapshot_json": resolved.snapshot_json,
            "parser_version": "1",
            "attempt_no": step.attempt_no,
            "fallback_no": step.fallback_no,
            "status": AttemptStatus.RUNNING,
            "started_at": now,
        }
        insert_result = self._db.table("recognition_attempts").insert(attempt_data).execute()
        attempt_id = insert_result.data[0]["id"]

        # Вызов провайдера
        response_format = None
        if resolved.parser_strategy in ("stamp_json", "image_json"):
            response_format = {"type": "json_object"}

        provider = create_provider(source_config)
        try:
            ocr_result = asyncio.run(
                provider.recognize_block(
                    image_b64=image_b64,
                    system_prompt=resolved.system_prompt,
                    user_prompt=resolved.user_prompt,
                    model_id=step.model_name,
                    response_format=response_format,
                )
            )
        except Exception as exc:
            logger.error("OCR call failed: block=%s, source=%s: %s", block_data["id"], step.source_id, exc)
            ocr_result = RecognizeResult(
                text="",
                is_error=True,
                error_code="call_exception",
                error_message=str(exc),
            )
        finally:
            try:
                asyncio.run(provider.close())
            except Exception:
                pass

        return attempt_id, ocr_result

    def _write_attempt(
        self,
        block_data: dict,
        step: _AttemptStep,
        prompt_template_id: str,
        status: str,
        ocr_result: RecognizeResult | None,
        error_code: str | None,
        error_message: str | None,
        snapshot: dict,
    ) -> str:
        """Вставить attempt без OCR вызова (skipped/failed early)."""
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "run_id": self._run_id,
            "block_id": block_data["id"],
            "geometry_rev": block_data["geometry_rev"],
            "source_id": step.source_id,
            "model_name": step.model_name,
            "prompt_template_id": prompt_template_id,
            "prompt_snapshot_json": snapshot,
            "parser_version": "1",
            "attempt_no": step.attempt_no,
            "fallback_no": step.fallback_no,
            "status": status,
            "error_code": error_code,
            "error_message": error_message,
            "started_at": now,
            "finished_at": now,
        }
        result = self._db.table("recognition_attempts").insert(data).execute()
        return result.data[0]["id"]

    def _update_attempt(
        self,
        attempt_id: str,
        status: str,
        vr: VerificationResult,
    ) -> None:
        """Обновить attempt после verification."""
        now = datetime.now(timezone.utc).isoformat()
        update: dict[str, Any] = {
            "status": status,
            "finished_at": now,
        }
        if vr.code != VerificationCode.OK:
            update["error_code"] = vr.code.value
            update["error_message"] = vr.details
        if vr.quality_flags:
            update["quality_flags_json"] = vr.quality_flags

        self._db.table("recognition_attempts").update(update).eq("id", attempt_id).execute()

    def _update_block_recognized(
        self,
        block_data: dict,
        result: RecognitionResult,
        signature: str,
    ) -> None:
        """Обновить блок после успешного распознавания."""
        # Снять selected_as_current с предыдущего attempt
        old_attempt_id = block_data.get("current_attempt_id")
        if old_attempt_id:
            self._db.table("recognition_attempts").update(
                {"selected_as_current": False}
            ).eq("id", old_attempt_id).execute()

        # Установить selected_as_current на новом
        if result.attempt_id:
            self._db.table("recognition_attempts").update(
                {"selected_as_current": True}
            ).eq("id", result.attempt_id).execute()

        self._db.table("blocks").update({
            "current_status": BlockStatus.RECOGNIZED,
            "current_text": result.normalized_text,
            "current_structured_json": result.structured_json,
            "current_render_html": result.render_html,
            "current_attempt_id": result.attempt_id,
            "content_rev": block_data["content_rev"] + 1,
            "last_recognition_signature": signature,
            "crop_sha256": result.crop_sha256,
            "crop_upload_state": CropUploadState.PENDING,
        }).eq("id", block_data["id"]).execute()

    def _update_block_terminal(
        self,
        block_data: dict,
        result: RecognitionResult,
        signature: str,
    ) -> None:
        """Обновить блок при terminal failure (manual_review / failed)."""
        self._db.table("blocks").update({
            "current_status": result.terminal_status,
            "crop_sha256": result.crop_sha256,
            "crop_upload_state": CropUploadState.PENDING,
            "last_recognition_signature": signature,
        }).eq("id", block_data["id"]).execute()


def _image_to_png_bytes(img: Image.Image) -> bytes:
    """Конвертировать PIL Image в PNG bytes."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
