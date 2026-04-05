"""R2 storage client — адаптация из legacy rd_core/r2_storage.py.

Предоставляет presigned URL для upload/download и базовые операции с объектами.
Секреты хранятся только на backend (правило #13 пролога).
"""

from __future__ import annotations

import logging
from pathlib import Path

import boto3
from botocore.config import Config

from ..config import Settings

logger = logging.getLogger(__name__)


class R2Client:
    """Клиент для Cloudflare R2 (S3-compatible)."""

    def __init__(self, settings: Settings) -> None:
        endpoint_url = f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"

        config = Config(
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=30,
            read_timeout=60,
            signature_version="s3v4",
        )

        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            config=config,
            region_name="auto",
        )
        self._bucket = settings.r2_bucket_name

        logger.info(
            "R2Client инициализирован",
            extra={"bucket": self._bucket, "endpoint": endpoint_url},
        )

    # ─── Presigned URLs ───────────────────────────────────────────────────

    def generate_presigned_put_url(
        self,
        key: str,
        content_type: str = "application/pdf",
        expires_in: int = 3600,
    ) -> str:
        """Presigned PUT URL для прямой загрузки с фронтенда в R2."""
        url: str = self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
        logger.debug("Presigned PUT URL для key=%s, expires_in=%d", key, expires_in)
        return url

    def generate_presigned_get_url(
        self,
        key: str,
        expires_in: int = 3600,
    ) -> str:
        """Presigned GET URL для скачивания оригинального PDF."""
        url: str = self._client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
            },
            ExpiresIn=expires_in,
        )
        logger.debug("Presigned GET URL для key=%s, expires_in=%d", key, expires_in)
        return url

    # ─── Операции с объектами ─────────────────────────────────────────────

    def head_object(self, key: str) -> dict:
        """Получить метаданные объекта (ContentLength, ETag и т.д.).

        Raises botocore.exceptions.ClientError если объект не найден.
        """
        response: dict = self._client.head_object(Bucket=self._bucket, Key=key)
        return response

    def download_file(self, key: str, local_path: str) -> None:
        """Скачать файл из R2 в локальный путь. Создаёт parent dirs."""
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        self._client.download_file(self._bucket, key, local_path)
        logger.info("Скачан %s → %s", key, local_path)
