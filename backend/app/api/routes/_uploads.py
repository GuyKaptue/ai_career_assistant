"""Shared helpers for upload endpoints."""

from __future__ import annotations

from fastapi import UploadFile

from app.core.errors import ValidationError


async def read_limited(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload, refusing anything larger than ``max_bytes``.

    The declared size is checked first and the read itself is capped at
    ``max_bytes + 1``, so an oversized body is never loaded into memory in full.
    """
    declared = getattr(file, "size", None)
    if declared is not None and declared > max_bytes:
        raise ValidationError(f"The file is larger than {max_bytes // (1024 * 1024)} MB.")
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValidationError(f"The file is larger than {max_bytes // (1024 * 1024)} MB.")
    return data
