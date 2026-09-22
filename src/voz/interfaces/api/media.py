"""Thin HTTP input adapter that uploads one original into a project.

The body is read as a raw byte stream (no multipart parsing) into a private
temporary file below a runtime directory chosen by the composition root. The
``ImportMedia`` use case then preserves, probes and persists it. Typed failures
from the ports are translated into stable error codes; the temporary file is
removed on every path and no host path ever reaches the response or the log.
"""

from __future__ import annotations

import logging
import os
import shutil
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import unquote
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from voz.application.import_media import ImportedMedia, ImportMedia
from voz.application.ports.media_probe import MediaProbeError, MediaProbeFailureCode
from voz.application.ports.media_storage import (
    MediaStorageError,
    MediaStorageErrorCode,
)
from voz.application.ports.repositories import ProjectRepository

DEFAULT_MAX_UPLOAD_BYTES: Final = 8 * 1024**3
FILENAME_HEADER: Final = "X-Voz-Filename"
_MAX_FILENAME_LENGTH: Final = 255
_UNSAFE_BIDI_CLASSES: Final = frozenset(
    {"LRE", "RLE", "LRO", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI"}
)
_PROBE_STATUS: Final[Mapping[MediaProbeFailureCode, tuple[int, str, str]]] = {
    MediaProbeFailureCode.INVALID_MEDIA: (
        422,
        "media_corrupt",
        "The uploaded file is not readable media.",
    ),
    MediaProbeFailureCode.NO_DECODABLE_AUDIO: (
        415,
        "media_unsupported",
        "The uploaded file contains no decodable audio.",
    ),
    MediaProbeFailureCode.TOOL_UNAVAILABLE: (
        503,
        "media_probe_unavailable",
        "Media inspection is not available right now.",
    ),
    MediaProbeFailureCode.TIMED_OUT: (
        503,
        "media_probe_unavailable",
        "Media inspection is not available right now.",
    ),
    MediaProbeFailureCode.INVALID_RESPONSE: (
        503,
        "media_probe_unavailable",
        "Media inspection is not available right now.",
    ),
}

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MediaUploadResponse:
    """Path-free description of one freshly imported original."""

    media_asset_id: UUID
    project_id: UUID
    filename: str
    media_type: str | None
    duration_ms: int | None
    sha256: str


def create_media_router(
    import_media: ImportMedia,
    projects: ProjectRepository,
    upload_dir: Path,
    *,
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
) -> APIRouter:
    """Expose ``POST /api/projects/{project_id}/media`` for raw-body uploads."""
    if type(max_upload_bytes) is not int or max_upload_bytes <= 0:
        raise ValueError("max_upload_bytes must be a positive integer")
    staging_root = Path(upload_dir).absolute()
    router = APIRouter(prefix="/api", tags=["media"])

    async def upload_media(project_id: UUID, request: Request) -> MediaUploadResponse:
        filename = _sanitized_filename(request.headers.get(FILENAME_HEADER))
        if await run_in_threadpool(projects.get, project_id) is None:
            raise _error(404, "project_not_found", "The project does not exist.")
        _reject_declared_oversize(
            request.headers.get("content-length"), max_upload_bytes
        )

        staging_directory = await run_in_threadpool(
            _create_staging_directory, staging_root
        )
        try:
            source = staging_directory / filename
            await _stream_body_to(request, source, max_upload_bytes)
            imported = await _import_or_translate(import_media, source, project_id)
        finally:
            await run_in_threadpool(
                shutil.rmtree, staging_directory, ignore_errors=True
            )
        return _response_for(imported)

    router.add_api_route(
        "/projects/{project_id}/media",
        upload_media,
        methods=["POST"],
        status_code=201,
        response_model=MediaUploadResponse,
    )
    return router


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _sanitized_filename(raw_header: str | None) -> str:
    """Accept a percent-encoded UTF-8 basename or reject the request."""
    if raw_header is None:
        raise _error(400, "filename_invalid", f"{FILENAME_HEADER} header is required.")
    try:
        name = unquote(raw_header, errors="strict").strip()
    except UnicodeDecodeError:
        name = ""
    unsafe_characters = any(
        unicodedata.category(character) in {"Cc", "Cf"}
        or unicodedata.bidirectional(character) in _UNSAFE_BIDI_CLASSES
        for character in name
    )
    if (
        not name
        or len(name) > _MAX_FILENAME_LENGTH
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or unsafe_characters
    ):
        raise _error(
            400,
            "filename_invalid",
            f"{FILENAME_HEADER} must be a plain file name without path separators.",
        )
    return name


def _reject_declared_oversize(content_length: str | None, limit: int) -> None:
    if content_length is None:
        return
    declared = content_length.strip()
    if declared.isascii() and declared.isdigit() and int(declared) > limit:
        raise _too_large()


def _too_large() -> HTTPException:
    return _error(413, "media_too_large", "The uploaded file exceeds the size limit.")


def _create_staging_directory(staging_root: Path) -> Path:
    staging_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = staging_root / f"upload-{uuid4()}"
    directory.mkdir(mode=0o700)
    return directory


async def _stream_body_to(request: Request, destination: Path, limit: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    received = 0
    with os.fdopen(os.open(destination, flags, 0o600), "wb") as output:
        async for chunk in request.stream():
            if not chunk:
                continue
            received += len(chunk)
            if received > limit:
                raise _too_large()
            output.write(chunk)
    if received == 0:
        raise _error(400, "media_empty", "The uploaded file is empty.")


async def _import_or_translate(
    import_media: ImportMedia,
    source: Path,
    project_id: UUID,
) -> ImportedMedia:
    try:
        return await run_in_threadpool(
            import_media.execute, source=source, project_id=project_id
        )
    except MediaProbeError as error:
        status_code, code, message = _PROBE_STATUS[error.code]
        raise _error(status_code, code, message) from None
    except MediaStorageError as error:
        if error.code is MediaStorageErrorCode.UNSAFE_DISPLAY_NAME:
            raise _error(
                400, "filename_invalid", "The file name cannot be stored safely."
            ) from None
        _logger.warning("Media storage rejected an upload: %s", error.code.value)
        raise _error(
            503,
            "media_storage_unavailable",
            "Media storage is not available right now.",
        ) from None
    except Exception as error:
        # Only the exception type is logged: messages may embed host paths.
        _logger.error("Media import failed: %s", type(error).__name__)
        raise _error(
            500, "media_import_failed", "The media import failed unexpectedly."
        ) from None


def _response_for(imported: ImportedMedia) -> MediaUploadResponse:
    asset = imported.media_asset
    return MediaUploadResponse(
        media_asset_id=asset.id,
        project_id=asset.project_id,
        filename=asset.display_name,
        media_type=asset.media_type,
        duration_ms=asset.duration_ms,
        sha256=asset.content_sha256,
    )


__all__ = [
    "DEFAULT_MAX_UPLOAD_BYTES",
    "FILENAME_HEADER",
    "MediaUploadResponse",
    "create_media_router",
]
