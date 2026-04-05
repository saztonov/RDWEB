"""Contracts — shared schemas для API."""

from .admin import AdminHealthResponse, ServiceHealthResponse, SystemEventListResponse, SystemEventResponse
from .auth import MeResponse, UserResponse, WorkspaceMemberInfo
from .common import ErrorResponse, PaginatedMeta
from .documents import (
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentPageResponse,
    DocumentResponse,
    DownloadUrlResponse,
    FinalizeRequest,
    FinalizeResponse,
    PagesListResponse,
    UploadUrlRequest,
    UploadUrlResponse,
)
from .health import HealthResponse, ReadinessResponse
from .workspaces import WorkspaceListResponse, WorkspaceResponse

__all__ = [
    # common
    "ErrorResponse",
    "PaginatedMeta",
    # health
    "HealthResponse",
    "ReadinessResponse",
    # auth
    "MeResponse",
    "UserResponse",
    "WorkspaceMemberInfo",
    # workspaces
    "WorkspaceListResponse",
    "WorkspaceResponse",
    # documents
    "DocumentDetailResponse",
    "DocumentListResponse",
    "DocumentPageResponse",
    "DocumentResponse",
    "DownloadUrlResponse",
    "FinalizeRequest",
    "FinalizeResponse",
    "PagesListResponse",
    "UploadUrlRequest",
    "UploadUrlResponse",
    # admin
    "AdminHealthResponse",
    "ServiceHealthResponse",
    "SystemEventListResponse",
    "SystemEventResponse",
]
