"""Contracts — shared schemas для API."""

from .admin import (
    AdminHealthResponse,
    AdminOcrSourceDetailResponse,
    AdminOcrSourceListResponse,
    AdminOcrSourceResponse,
    AdminRunBlockResponse,
    AdminRunDetailResponse,
    AdminRunListResponse,
    AdminRunResponse,
    BlockIncidentListResponse,
    BlockIncidentResponse,
    QueueSummaryResponse,
    ServiceHealthResponse,
    SystemEventListResponse,
    SystemEventResponse,
    WorkerHeartbeatResponse,
    WorkerSummaryResponse,
)
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
from .exports import ExportCreateRequest, ExportListResponse, ExportResponse
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
    "AdminOcrSourceDetailResponse",
    "AdminOcrSourceListResponse",
    "AdminOcrSourceResponse",
    "AdminRunBlockResponse",
    "AdminRunDetailResponse",
    "AdminRunListResponse",
    "AdminRunResponse",
    "BlockIncidentListResponse",
    "BlockIncidentResponse",
    "QueueSummaryResponse",
    "ServiceHealthResponse",
    "SystemEventListResponse",
    "SystemEventResponse",
    "WorkerHeartbeatResponse",
    "WorkerSummaryResponse",
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
    # exports
    "ExportCreateRequest",
    "ExportListResponse",
    "ExportResponse",
]
