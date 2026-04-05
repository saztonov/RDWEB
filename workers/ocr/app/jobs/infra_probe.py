"""Периодический healthcheck инфраструктурных сервисов.

Проверяет: Redis, Supabase, R2, OpenRouter.
Запись в service_health_checks + Redis pub/sub.
Запускается Celery beat каждые 60 секунд.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import redis
import httpx

from ..celery_app import celery_app
from ..config import get_worker_settings
from ..infra.db import get_db

logger = logging.getLogger(__name__)


def _get_redis_pubsub_client() -> redis.Redis:
    """Отдельный Redis client для pub/sub (не broker)."""
    settings = get_worker_settings()
    return redis.from_url(settings.celery_broker_url, decode_responses=True)


def _publish_health(r: redis.Redis, results: list[dict]) -> None:
    """Опубликовать результаты в Redis pub/sub."""
    try:
        r.publish("admin:health", json.dumps(results, default=str))
    except Exception:
        logger.warning("Не удалось опубликовать health в Redis pub/sub", exc_info=True)


def _probe_redis(settings) -> dict:
    """Проверка Redis PING."""
    start = time.monotonic()
    try:
        r = redis.from_url(settings.celery_broker_url, decode_responses=True, socket_timeout=5)
        r.ping()
        elapsed = int((time.monotonic() - start) * 1000)
        return {"service_name": "infra:redis", "status": "healthy", "response_time_ms": elapsed}
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return {
            "service_name": "infra:redis",
            "status": "unavailable",
            "response_time_ms": elapsed,
            "details_json": {"error": str(exc)},
        }


def _probe_supabase(settings) -> dict:
    """Проверка Supabase SELECT 1."""
    start = time.monotonic()
    try:
        sb = get_db()
        sb.table("workspaces").select("id").limit(1).execute()
        elapsed = int((time.monotonic() - start) * 1000)
        return {"service_name": "infra:supabase", "status": "healthy", "response_time_ms": elapsed}
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return {
            "service_name": "infra:supabase",
            "status": "unavailable",
            "response_time_ms": elapsed,
            "details_json": {"error": str(exc)},
        }


def _probe_r2(settings) -> dict:
    """Проверка R2 HeadBucket."""
    start = time.monotonic()
    if not settings.r2_account_id or not settings.r2_access_key_id:
        return {
            "service_name": "infra:r2",
            "status": "unavailable",
            "response_time_ms": 0,
            "details_json": {"error": "R2 credentials не настроены"},
        }
    try:
        import boto3
        s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        )
        s3.head_bucket(Bucket=settings.r2_bucket_name)
        elapsed = int((time.monotonic() - start) * 1000)
        return {"service_name": "infra:r2", "status": "healthy", "response_time_ms": elapsed}
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return {
            "service_name": "infra:r2",
            "status": "unavailable",
            "response_time_ms": elapsed,
            "details_json": {"error": str(exc)},
        }


def _probe_openrouter(settings) -> dict:
    """Проверка OpenRouter API доступности."""
    start = time.monotonic()
    if not settings.openrouter_api_key:
        return {
            "service_name": "infra:openrouter",
            "status": "unavailable",
            "response_time_ms": 0,
            "details_json": {"error": "OPENROUTER_API_KEY не настроен"},
        }
    try:
        resp = httpx.get(
            f"{settings.openrouter_base_url}/api/v1/models",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            timeout=10,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        if resp.status_code == 200:
            return {"service_name": "infra:openrouter", "status": "healthy", "response_time_ms": elapsed}
        return {
            "service_name": "infra:openrouter",
            "status": "degraded",
            "response_time_ms": elapsed,
            "details_json": {"status_code": resp.status_code},
        }
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return {
            "service_name": "infra:openrouter",
            "status": "unavailable",
            "response_time_ms": elapsed,
            "details_json": {"error": str(exc)},
        }


@celery_app.task(name="ocr.probe_infra_health", ignore_result=True)
def probe_infra_health() -> dict:
    """Периодический healthcheck инфраструктуры: Redis, Supabase, R2, OpenRouter."""
    settings = get_worker_settings()
    if not settings.supabase_url or not settings.supabase_key:
        logger.warning("probe_infra_health: Supabase не настроен")
        return {"status": "skipped", "reason": "no_supabase"}

    sb = get_db()
    now = datetime.now(timezone.utc).isoformat()

    probes = [
        _probe_redis(settings),
        _probe_supabase(settings),
        _probe_r2(settings),
        _probe_openrouter(settings),
    ]

    for probe_result in probes:
        try:
            sb.table("service_health_checks").insert({
                "service_name": probe_result["service_name"],
                "status": probe_result["status"],
                "response_time_ms": probe_result.get("response_time_ms"),
                "details_json": probe_result.get("details_json"),
                "checked_at": now,
            }).execute()
        except Exception:
            logger.exception(
                "Не удалось записать health check для %s", probe_result["service_name"]
            )

    # Pub/sub уведомление
    try:
        r = _get_redis_pubsub_client()
        _publish_health(r, probes)
    except Exception:
        pass

    summary = {p["service_name"]: p["status"] for p in probes}
    logger.info("Infrastructure health probe: %s", summary)
    return summary
