"""Permissions — проверки доступа и audit helpers."""

from .audit import stamp_created, stamp_updated, write_block_event, write_system_event
from .checks import (
    get_document_workspace_id,
    get_workspace_role,
    require_document_access,
    require_workspace_admin,
    require_workspace_member,
)

__all__ = [
    # checks
    "get_document_workspace_id",
    "get_workspace_role",
    "require_document_access",
    "require_workspace_admin",
    "require_workspace_member",
    # audit
    "stamp_created",
    "stamp_updated",
    "write_block_event",
    "write_system_event",
]
