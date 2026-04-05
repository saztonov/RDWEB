"""API routes — агрегатор всех роутеров."""

from fastapi import APIRouter

from .admin import router as admin_router
from .blocks import router as blocks_router
from .documents import router as documents_router
from .me import router as me_router
from .workspaces import router as workspaces_router

api_router = APIRouter(prefix="/api")
api_router.include_router(me_router)
api_router.include_router(workspaces_router)
api_router.include_router(documents_router)
api_router.include_router(blocks_router)
api_router.include_router(admin_router)
