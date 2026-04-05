"""API routes — агрегатор всех роутеров."""

from fastapi import APIRouter

from .admin import router as admin_router
from .admin_incidents import router as admin_incidents_router
from .admin_runs import router as admin_runs_router
from .admin_sources import router as admin_sources_router
from .admin_sse import router as admin_sse_router
from .blocks import router as blocks_router
from .documents import router as documents_router
from .exports import router as exports_router
from .recognition import router as recognition_router
from .me import router as me_router
from .ocr_sources import router as ocr_sources_router
from .profile_routes import router as profile_routes_router
from .prompt_templates import router as prompt_templates_router
from .workspaces import router as workspaces_router

api_router = APIRouter(prefix="/api")
api_router.include_router(me_router)
api_router.include_router(workspaces_router)
api_router.include_router(documents_router)
api_router.include_router(exports_router)
api_router.include_router(blocks_router)
api_router.include_router(recognition_router)
api_router.include_router(ocr_sources_router)
api_router.include_router(admin_router)
api_router.include_router(admin_sources_router)
api_router.include_router(admin_runs_router)
api_router.include_router(admin_incidents_router)
api_router.include_router(admin_sse_router)
api_router.include_router(prompt_templates_router)
api_router.include_router(profile_routes_router)
