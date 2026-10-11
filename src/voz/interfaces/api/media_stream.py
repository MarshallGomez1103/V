"""Thin HTTP output adapter that streams one immutable original inline.

The browser player asks for ``/api/media/{id}/original``; the router looks the
asset up, resolves the infrastructure-only path through the storage adapter and
delegates byte serving (including ``Range`` requests) to Starlette's
``FileResponse``. No host path, ``Content-Disposition`` or traceback ever
reaches the response.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from starlette.responses import FileResponse

from voz.application.library import media_type_or_guess
from voz.application.ports.repositories import MediaAssetRepository
from voz.infrastructure.media_storage import FileSystemMediaStorage
from voz.interfaces.api.errors import api_error

_FALLBACK_MEDIA_TYPE: Final = "application/octet-stream"
_HEADERS: Final = {"Cache-Control": "private, max-age=3600", "Accept-Ranges": "bytes"}


def create_media_stream_router(
    media_assets: MediaAssetRepository,
    storage: FileSystemMediaStorage,
) -> APIRouter:
    """Expose ``GET /api/media/{media_asset_id}/original`` for inline playback."""
    router = APIRouter(prefix="/api", tags=["media"])

    async def stream_original(media_asset_id: UUID) -> FileResponse:
        asset = await run_in_threadpool(media_assets.get, media_asset_id)
        if asset is None:
            raise api_error(
                404, "media_asset_not_found", "The media asset does not exist."
            )
        path = storage.original_path_for(asset.project_id, asset.id)
        if not await run_in_threadpool(path.is_file):
            raise api_error(
                404, "media_file_missing", "The original file is not available."
            )
        return FileResponse(
            path,
            media_type=asset.media_type or _FALLBACK_MEDIA_TYPE,
            headers=dict(_HEADERS),
        )

    async def media_info(media_asset_id: UUID) -> dict[str, object]:
        """Path-free metadata, so a reopened job can show its recording."""
        asset = await run_in_threadpool(media_assets.get, media_asset_id)
        if asset is None:
            raise api_error(
                404, "media_asset_not_found", "The media asset does not exist."
            )
        return {
            "media_asset_id": str(asset.id),
            "project_id": str(asset.project_id),
            "filename": asset.display_name,
            "media_type": media_type_or_guess(asset.media_type, asset.display_name),
            "duration_ms": asset.duration_ms,
            "sha256": asset.content_sha256,
            "size_bytes": asset.size_bytes,
        }

    router.add_api_route("/media/{media_asset_id}", media_info, methods=["GET"])
    router.add_api_route(
        "/media/{media_asset_id}/original",
        stream_original,
        methods=["GET"],
        response_class=FileResponse,
    )
    return router


__all__ = ["create_media_stream_router"]
