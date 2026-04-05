"""Local PDF cache manager — хранит локальные копии PDF для OCR runtime.

Переиспользуется API сервером (finalize) и Celery worker (OCR tasks).
Не зависит от PyMuPDF — только файловое кеширование.

Паттерн:
- Один файл на document_id: {base_dir}/{document_id}/original.pdf
- Sidecar .etag файл для проверки актуальности
- Per-document threading.Lock для thread safety
- TTL cleanup для удаления устаревших кешей
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


class PdfCacheManager:
    """Thread-safe локальный кеш PDF файлов с TTL и etag awareness."""

    def __init__(self, base_dir: Path, ttl_seconds: int = 3600) -> None:
        self._base_dir = base_dir
        self._ttl = ttl_seconds
        self._global_lock = threading.Lock()
        self._file_locks: dict[str, threading.Lock] = {}
        self._base_dir.mkdir(parents=True, exist_ok=True)
        logger.info("PdfCacheManager: base_dir=%s, ttl=%ds", base_dir, ttl_seconds)

    def _get_file_lock(self, document_id: str) -> threading.Lock:
        """Получить или создать lock для конкретного документа."""
        with self._global_lock:
            if document_id not in self._file_locks:
                self._file_locks[document_id] = threading.Lock()
            return self._file_locks[document_id]

    def get_local_path(self, document_id: str) -> Path:
        """Путь к локальной копии PDF."""
        return self._base_dir / document_id / "original.pdf"

    def _etag_path(self, document_id: str) -> Path:
        """Путь к sidecar файлу с etag."""
        return self._base_dir / document_id / ".etag"

    def _read_stored_etag(self, document_id: str) -> str | None:
        """Прочитать сохранённый etag из sidecar файла."""
        path = self._etag_path(document_id)
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        return None

    def _write_etag(self, document_id: str, etag: str) -> None:
        """Сохранить etag в sidecar файл."""
        path = self._etag_path(document_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(etag, encoding="utf-8")

    def ensure_cached(
        self,
        document_id: str,
        download_fn: Callable[[str], None],
        etag: str | None = None,
    ) -> Path:
        """Убедиться что PDF закеширован локально.

        Args:
            document_id: UUID документа.
            download_fn: Функция fn(local_path_str) которая скачивает PDF.
            etag: ETag из R2 head_object. Если не совпадает — перекачивается.

        Returns:
            Path к локальному PDF файлу.
        """
        lock = self._get_file_lock(document_id)
        with lock:
            local_path = self.get_local_path(document_id)
            need_download = False

            if not local_path.exists():
                need_download = True
                logger.debug("Кеш отсутствует для %s", document_id)
            elif etag is not None:
                stored_etag = self._read_stored_etag(document_id)
                if stored_etag != etag:
                    need_download = True
                    logger.info(
                        "ETag mismatch для %s: stored=%s, remote=%s",
                        document_id, stored_etag, etag,
                    )

            if need_download:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                download_fn(str(local_path))
                if etag is not None:
                    self._write_etag(document_id, etag)
                logger.info("PDF закеширован: %s (%d bytes)", document_id, local_path.stat().st_size)

            return local_path

    def cleanup_expired(self) -> int:
        """Удалить кеши старше TTL. Возвращает количество удалённых."""
        removed = 0
        now = time.time()
        if not self._base_dir.exists():
            return 0

        for doc_dir in self._base_dir.iterdir():
            if not doc_dir.is_dir():
                continue
            pdf_path = doc_dir / "original.pdf"
            if not pdf_path.exists():
                continue
            age = now - pdf_path.stat().st_mtime
            if age > self._ttl:
                document_id = doc_dir.name
                lock = self._get_file_lock(document_id)
                if lock.acquire(blocking=False):
                    try:
                        shutil.rmtree(doc_dir, ignore_errors=True)
                        removed += 1
                        logger.debug("Удалён устаревший кеш: %s (age=%.0fs)", document_id, age)
                    finally:
                        lock.release()
                        with self._global_lock:
                            self._file_locks.pop(document_id, None)

        if removed:
            logger.info("Cleanup: удалено %d устаревших кешей", removed)
        return removed

    def invalidate(self, document_id: str) -> None:
        """Удалить кеш конкретного документа."""
        lock = self._get_file_lock(document_id)
        with lock:
            doc_dir = self._base_dir / document_id
            if doc_dir.exists():
                shutil.rmtree(doc_dir, ignore_errors=True)
                logger.info("Кеш инвалидирован: %s", document_id)
        with self._global_lock:
            self._file_locks.pop(document_id, None)
