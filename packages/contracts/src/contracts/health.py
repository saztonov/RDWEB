"""Schemas для health endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    ok: bool


class ReadinessChecks(BaseModel):
    redis: bool
    supabase: bool
    config: bool


class ReadinessResponse(BaseModel):
    ready: bool
    checks: ReadinessChecks
