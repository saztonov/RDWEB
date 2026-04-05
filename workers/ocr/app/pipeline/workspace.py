"""Local workspace для хранения temp crop-ов.

Структура:
  {base_dir}/{run_id}/{page_number}/{block_id}/
    crop.png
    debug.json
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class Workspace:
    """Локальный workspace для одной page task."""

    def __init__(self, base_dir: str, run_id: str, page_number: int) -> None:
        self._root = Path(base_dir) / run_id / str(page_number)

    @property
    def root(self) -> Path:
        return self._root

    def ensure_dirs(self, block_ids: list[str]) -> None:
        """Создать директории для всех блоков."""
        for block_id in block_ids:
            (self._root / block_id).mkdir(parents=True, exist_ok=True)

    def block_dir(self, block_id: str) -> Path:
        return self._root / block_id

    def crop_path(self, block_id: str) -> Path:
        return self._root / block_id / "crop.png"

    def debug_path(self, block_id: str) -> Path:
        return self._root / block_id / "debug.json"

    def save_debug(self, block_id: str, data: dict[str, Any]) -> None:
        """Сохранить debug metadata для блока."""
        path = self.debug_path(block_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def cleanup(self) -> None:
        """Удалить workspace после завершения task."""
        if self._root.exists():
            shutil.rmtree(self._root, ignore_errors=True)
            logger.debug("Workspace cleaned: %s", self._root)

            # Попробовать удалить родительскую (run_id) если пуста
            run_dir = self._root.parent
            try:
                if run_dir.exists() and not any(run_dir.iterdir()):
                    run_dir.rmdir()
            except OSError:
                pass
