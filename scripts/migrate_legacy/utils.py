"""Утилиты для migration: детекция ошибок, прогресс, state файл."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

console = Console()

# ─────────────────────────────────────────────────────────────────────
# OCR error detection (из legacy rd_core/ocr_result.py)
# ─────────────────────────────────────────────────────────────────────

ERROR_PREFIX = "[Ошибка"
NON_RETRIABLE_PREFIX = "[НеПовторяемая"

_ERROR_PATTERNS = [
    re.compile(r"^\[Ошибка:"),
    re.compile(r"^\[НеПовторяемая ошибка:"),
    re.compile(r"^\[Error:"),
]


def is_ocr_error(text: Optional[str]) -> bool:
    """Текст содержит маркер ошибки OCR."""
    if not text:
        return False
    stripped = text.strip()
    return any(p.search(stripped) for p in _ERROR_PATTERNS)


def is_non_retriable_error(text: Optional[str]) -> bool:
    """Неповторяемая ошибка."""
    if not text:
        return False
    return NON_RETRIABLE_PREFIX in text


def is_ocr_success(text: Optional[str]) -> bool:
    """Текст — успешный результат OCR (не пусто, без ошибок)."""
    if not text or not text.strip():
        return False
    return not is_ocr_error(text)


def determine_block_status(ocr_text: Optional[str], is_correction: bool) -> str:
    """Определить current_status блока по legacy данным."""
    if is_correction:
        return "pending"
    if ocr_text is None or not ocr_text.strip():
        return "pending"
    if is_ocr_error(ocr_text):
        return "failed"
    return "recognized"


# ─────────────────────────────────────────────────────────────────────
# UUID generation
# ─────────────────────────────────────────────────────────────────────

def new_uuid() -> str:
    """Сгенерировать новый UUID v4."""
    return str(uuid4())


def now_utc() -> str:
    """Текущее время UTC в ISO формате."""
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────
# State файл (маппинг legacy_node_id → new_document_id)
# ─────────────────────────────────────────────────────────────────────

class MigrationState:
    """Персистентное состояние миграции: маппинг legacy → new ID."""

    def __init__(self, state_file: str):
        self._path = Path(state_file)
        self._data: dict[str, Any] = {"documents": {}, "blocks": {}, "prompts": {}, "runs": {}}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def has_document(self, legacy_node_id: str) -> bool:
        return legacy_node_id in self._data.get("documents", {})

    def add_document(self, legacy_node_id: str, new_document_id: str) -> None:
        self._data.setdefault("documents", {})[legacy_node_id] = new_document_id

    def get_document_id(self, legacy_node_id: str) -> Optional[str]:
        return self._data.get("documents", {}).get(legacy_node_id)

    def has_run(self, legacy_node_id: str) -> bool:
        return legacy_node_id in self._data.get("runs", {})

    def add_run(self, legacy_node_id: str, run_id: str) -> None:
        self._data.setdefault("runs", {})[legacy_node_id] = run_id

    def get_run_id(self, legacy_node_id: str) -> Optional[str]:
        return self._data.get("runs", {}).get(legacy_node_id)

    @property
    def stats(self) -> dict[str, int]:
        return {k: len(v) for k, v in self._data.items()}


# ─────────────────────────────────────────────────────────────────────
# Progress helpers
# ─────────────────────────────────────────────────────────────────────

def create_progress() -> Progress:
    """Создать Rich progress bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )


# ─────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────

class MigrationSummary:
    """Счётчики результатов миграции."""

    def __init__(self):
        self.documents_created = 0
        self.documents_skipped = 0
        self.pages_created = 0
        self.blocks_created = 0
        self.blocks_skipped_table = 0
        self.blocks_skipped_other = 0
        self.attempts_created = 0
        self.runs_created = 0
        self.prompts_created = 0
        self.prompts_skipped = 0
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def print_report(self, dry_run: bool = False) -> None:
        prefix = "[DRY-RUN] " if dry_run else ""
        console.print(f"\n{'='*60}")
        console.print(f"[bold]{prefix}Результаты миграции[/bold]")
        console.print(f"{'='*60}")
        console.print(f"  Документов создано:     {self.documents_created}")
        console.print(f"  Документов пропущено:   {self.documents_skipped}")
        console.print(f"  Страниц создано:        {self.pages_created}")
        console.print(f"  Блоков создано:          {self.blocks_created}")
        console.print(f"  Блоков пропущено (table): {self.blocks_skipped_table}")
        console.print(f"  Блоков пропущено (other): {self.blocks_skipped_other}")
        console.print(f"  Recognition runs:        {self.runs_created}")
        console.print(f"  Recognition attempts:    {self.attempts_created}")
        console.print(f"  Промптов создано:        {self.prompts_created}")
        console.print(f"  Промптов пропущено:      {self.prompts_skipped}")

        if self.warnings:
            console.print(f"\n[yellow]Предупреждения ({len(self.warnings)}):[/yellow]")
            for w in self.warnings[:20]:
                console.print(f"  ⚠ {w}")
            if len(self.warnings) > 20:
                console.print(f"  ... и ещё {len(self.warnings) - 20}")

        if self.errors:
            console.print(f"\n[red]Ошибки ({len(self.errors)}):[/red]")
            for e in self.errors[:20]:
                console.print(f"  ✗ {e}")
            if len(self.errors) > 20:
                console.print(f"  ... и ещё {len(self.errors) - 20}")
