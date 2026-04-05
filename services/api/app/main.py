"""FastAPI сервер для OCR Web MVP.

Паттерны startup/shutdown, health endpoints и middleware
адаптированы из legacy_project/services/remote_ocr/server/main.py.
"""

from __future__ import annotations

import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from ocr_core import PdfCacheManager

from .auth.supabase_client import get_supabase, init_supabase
from .config import get_settings
from .logging_config import get_logger, setup_logging
from .middleware import RequestTimingMiddleware
from .routes import api_router
from .services.r2_client import R2Client

setup_logging()
_logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifecycle: инициализация при старте, cleanup при остановке."""
    settings = get_settings()

    # Инициализация Supabase client (service_role, обходит RLS)
    if settings.supabase_url and settings.supabase_key:
        init_supabase(settings.supabase_url, settings.supabase_key)

    # Инициализация R2 client для presigned URL и файловых операций
    if settings.r2_account_id and settings.r2_access_key_id:
        app.state.r2_client = R2Client(settings)
    else:
        app.state.r2_client = None
        _logger.warning("R2 не сконфигурирован — document upload/download недоступны")

    # Инициализация PDF cache manager
    cache_dir = Path(tempfile.gettempdir()) / "rdweb-pdf-cache"
    app.state.pdf_cache = PdfCacheManager(base_dir=cache_dir, ttl_seconds=3600)

    _logger.info(
        "Server starting",
        extra={
            "event": "server_startup",
            "config": {
                "supabase_configured": bool(settings.supabase_url),
                "r2_configured": bool(settings.r2_account_id),
                "redis_url": settings.redis_url.split("@")[-1],  # без пароля
                "has_openrouter_key": bool(settings.openrouter_api_key),
                "has_datalab_key": bool(settings.datalab_api_key),
                "has_chandra_url": bool(settings.chandra_base_url),
                "pdf_cache_dir": str(cache_dir),
            },
        },
    )

    # TODO: Фоновые задачи (zombie detector, model unloader) — Phase 3

    yield

    # Cleanup: очистка expired PDF кешей
    if app.state.pdf_cache:
        app.state.pdf_cache.cleanup_expired()

    _logger.info("Server shutting down", extra={"event": "server_shutdown"})


app = FastAPI(
    title="rdweb-api",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS для dev (Vite на :3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestTimingMiddleware)

# Business API routes (auth-protected)
app.include_router(api_router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    _logger.error("Validation error on %s %s: %s", request.method, request.url.path, exc.errors())
    return JSONResponse(status_code=400, content={"detail": exc.errors()})


@app.get("/health")
def health() -> dict:
    """Liveness check."""
    return {"ok": True}


@app.get("/health/ready")
async def readiness() -> JSONResponse:
    """Readiness check — Redis + Supabase + OCR config."""
    settings = get_settings()
    checks: dict[str, bool] = {"redis": False, "supabase": False, "config": False}

    # Redis ping
    try:
        import redis as redis_lib

        r = redis_lib.from_url(settings.redis_url, socket_connect_timeout=3)
        r.ping()
        r.close()
        checks["redis"] = True
    except Exception:
        _logger.warning("Readiness: Redis ping failed", exc_info=True)

    # Supabase check
    try:
        sb = get_supabase()
        sb.table("workspaces").select("id", count="exact").limit(1).execute()
        checks["supabase"] = True
    except Exception:
        _logger.warning("Readiness: Supabase check failed", exc_info=True)

    # Config: хотя бы один OCR провайдер настроен
    checks["config"] = bool(settings.openrouter_api_key or settings.datalab_api_key or settings.chandra_base_url)

    ready = all(checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"ready": ready, "checks": checks},
    )


@app.get("/queue")
def queue_status() -> dict:
    """Queue status для мониторинга backpressure."""
    try:
        import redis as redis_lib

        settings = get_settings()
        r = redis_lib.from_url(settings.redis_url, socket_connect_timeout=3)
        size = r.llen("celery") or 0
        r.close()
        return {"can_accept": True, "size": size, "max": 100}
    except Exception:
        return {"can_accept": False, "size": -1, "max": 100, "error": "Redis unavailable"}
