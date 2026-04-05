"""Contracts — shared schemas для API."""

from .admin import AdminHealthResponse, ServiceHealthResponse, SystemEventListResponse, SystemEventResponse
from .auth import MeResponse, UserResponse, WorkspaceMemberInfo
from .blocks import (
    AcceptAttemptRequest,
    BlockDetailResponse,
    DirtyBlocksSummaryResponse,
    ManualEditRequest,
    RecognitionAttemptListResponse,
    RecognitionAttemptResponse,
    RecognitionRunCreateRequest,
    RecognitionRunListResponse,
    RecognitionRunResponse,
    RerunBlockRequest,
    ToggleLockRequest,
)
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
from .prompt_templates import (
    BlockPromptOverrideRequest,
    BlockRef,
    ParserStrategy,
    ProfileRoutePatchRequest,
    ProfileRouteListResponse,
    ProfileRouteRef,
    ProfileRouteResponse,
    PromptTemplateCloneRequest,
    PromptTemplateCreateRequest,
    PromptTemplateListResponse,
    PromptTemplateNewVersionRequest,
    PromptTemplateResponse,
    PromptTemplateUsageResponse,
    PromptTemplateVersionsResponse,
)
from .ocr_sources import (
    HealthCheckResponse,
    OcrSourceListResponse,
    OcrSourceModelResponse,
    OcrSourceModelsListResponse,
    OcrSourceResponse,
)
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
    # blocks — manual edit, lock, attempts, recognition
    "AcceptAttemptRequest",
    "BlockDetailResponse",
    "DirtyBlocksSummaryResponse",
    "ManualEditRequest",
    "RecognitionAttemptListResponse",
    "RecognitionAttemptResponse",
    "RecognitionRunCreateRequest",
    "RecognitionRunListResponse",
    "RecognitionRunResponse",
    "RerunBlockRequest",
    "ToggleLockRequest",
    # prompt templates
    "BlockPromptOverrideRequest",
    "BlockRef",
    "ParserStrategy",
    "ProfileRoutePatchRequest",
    "ProfileRouteListResponse",
    "ProfileRouteRef",
    "ProfileRouteResponse",
    "PromptTemplateCloneRequest",
    "PromptTemplateCreateRequest",
    "PromptTemplateListResponse",
    "PromptTemplateNewVersionRequest",
    "PromptTemplateResponse",
    "PromptTemplateUsageResponse",
    "PromptTemplateVersionsResponse",
    # ocr sources
    "OcrSourceResponse",
    "OcrSourceListResponse",
    "OcrSourceModelResponse",
    "OcrSourceModelsListResponse",
    "HealthCheckResponse",
]
