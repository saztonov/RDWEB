"""Тесты pipeline signature — idempotency."""

from __future__ import annotations

import pytest

from app.pipeline.signature import build_pipeline_signature, compute_crop_sha256, is_signature_match


def test_deterministic():
    """Одинаковые входные → одинаковый hash."""
    sig1 = build_pipeline_signature(1, "text", "src1", "model1", "pt1", 1, "1", "abc123")
    sig2 = build_pipeline_signature(1, "text", "src1", "model1", "pt1", 1, "1", "abc123")
    assert sig1 == sig2


def test_geometry_change():
    """Изменение geometry_rev → другая signature."""
    sig1 = build_pipeline_signature(1, "text", "src1", "model1", "pt1", 1, "1", "abc123")
    sig2 = build_pipeline_signature(2, "text", "src1", "model1", "pt1", 1, "1", "abc123")
    assert sig1 != sig2


def test_model_change():
    """Изменение model → другая signature."""
    sig1 = build_pipeline_signature(1, "text", "src1", "model_a", "pt1", 1, "1", "abc123")
    sig2 = build_pipeline_signature(1, "text", "src1", "model_b", "pt1", 1, "1", "abc123")
    assert sig1 != sig2


def test_crop_change():
    """Изменение crop_sha256 → другая signature."""
    sig1 = build_pipeline_signature(1, "text", "src1", "model1", "pt1", 1, "1", "hash_a")
    sig2 = build_pipeline_signature(1, "text", "src1", "model1", "pt1", 1, "1", "hash_b")
    assert sig1 != sig2


def test_prompt_version_change():
    """Изменение prompt version → другая signature."""
    sig1 = build_pipeline_signature(1, "text", "src1", "model1", "pt1", 1, "1", "abc")
    sig2 = build_pipeline_signature(1, "text", "src1", "model1", "pt1", 2, "1", "abc")
    assert sig1 != sig2


def test_is_signature_match_recognized():
    """Match если recognized + same signature."""
    block = {"last_recognition_signature": "abc", "current_status": "recognized"}
    assert is_signature_match(block, "abc") is True


def test_is_signature_match_different():
    """No match если signature отличается."""
    block = {"last_recognition_signature": "abc", "current_status": "recognized"}
    assert is_signature_match(block, "xyz") is False


def test_is_signature_match_null():
    """No match если signature is None."""
    block = {"last_recognition_signature": None, "current_status": "pending"}
    assert is_signature_match(block, "abc") is False


def test_is_signature_match_not_recognized():
    """No match если status ≠ recognized."""
    block = {"last_recognition_signature": "abc", "current_status": "failed"}
    assert is_signature_match(block, "abc") is False


def test_crop_sha256():
    """SHA256 от bytes."""
    sha = compute_crop_sha256(b"test image data")
    assert len(sha) == 64
    assert sha == compute_crop_sha256(b"test image data")
    assert sha != compute_crop_sha256(b"different data")
