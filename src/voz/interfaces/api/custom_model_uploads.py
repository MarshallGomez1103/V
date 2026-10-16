"""Raw folder uploads without multipart dependencies or exposed host paths."""

from collections.abc import AsyncIterable, Callable
from contextlib import AbstractContextManager
from typing import Annotated, Protocol

from fastapi import APIRouter, Path, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from voz.application.import_custom_model import ImportCustomModel
from voz.application.ports.custom_model_upload import (
    CustomModelUploadFile,
    CustomModelUploadReceipt,
    CustomModelUploadRequest,
)
from voz.application.ports.custom_models import (
    CustomModelError,
    CustomModelPreview,
    CustomModelRequest,
)
from voz.application.ports.model_installation import ModelInstallationError
from voz.interfaces.api.errors import api_error
from voz.interfaces.api.models import PrivateModelRoute


class Uploads(Protocol):
    def create(self, request: CustomModelUploadRequest) -> CustomModelUploadReceipt: ...

    async def write(
        self, upload_id: str, index: int, chunks: AsyncIterable[bytes]
    ) -> None: ...

    def request(self, upload_id: str) -> CustomModelRequest: ...

    def discard(self, upload_id: str) -> None: ...

    def hold(self, upload_id: str) -> AbstractContextManager[None]: ...


class FileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=512)
    size_bytes: int = Field(gt=0, le=16 * 1024**3, strict=True)


class FolderRequest(BaseModel):
    engine: str = Field(max_length=64)
    family: str = Field(max_length=64)
    display_name: str = Field(max_length=128)
    license: str = Field(default="unknown", max_length=512)
    file_roles: dict[str, str] = Field(default_factory=dict[str, str], max_length=32)
    files: list[FileRequest] = Field(min_length=1, max_length=10_000)


UploadId = Annotated[str, Path(pattern="^[0-9a-f]{32}$")]
FileIndex = Annotated[int, Path(ge=0, lt=10_000)]


def _translate(error: CustomModelError | ModelInstallationError) -> Exception:
    code = str(error.code)
    status = (
        507
        if code == "disk_space_insufficient"
        else 404
        if code in {"custom_model_upload_expired", "custom_model_upload_not_found"}
        else 413
        if code == "custom_model_upload_too_large"
        else 422
    )
    return api_error(status, code, error.user_message)


def create_custom_model_uploads_router(
    uploads: Uploads,
    importer: ImportCustomModel,
    *,
    runtime_available: Callable[[str], bool],
) -> APIRouter:
    router = APIRouter(
        prefix="/api/models/custom/uploads",
        tags=["models"],
        route_class=PrivateModelRoute,
    )

    def create(body: FolderRequest) -> CustomModelUploadReceipt:
        try:
            if not runtime_available(body.engine):
                raise CustomModelError(
                    "custom_model_runtime_unavailable",
                    "The selected model engine is not installed.",
                )
            return uploads.create(
                CustomModelUploadRequest(
                    engine=body.engine,
                    family=body.family,
                    display_name=body.display_name,
                    license=body.license,
                    file_roles=body.file_roles,
                    files=tuple(
                        CustomModelUploadFile(item.name, item.size_bytes)
                        for item in body.files
                    ),
                )
            )
        except (CustomModelError, ModelInstallationError) as error:
            raise _translate(error) from None

    async def write(
        upload_id: UploadId, index: FileIndex, request: Request
    ) -> Response:
        try:
            await uploads.write(upload_id, index, request.stream())
        except (CustomModelError, ModelInstallationError) as error:
            raise _translate(error) from None
        return Response(status_code=204)

    def preview(upload_id: UploadId) -> CustomModelPreview:
        try:
            with uploads.hold(upload_id):
                return importer.prepare(uploads.request(upload_id))
        except (CustomModelError, ModelInstallationError) as error:
            raise _translate(error) from None

    async def discard(upload_id: UploadId) -> Response:
        try:
            await run_in_threadpool(uploads.discard, upload_id)
        except (CustomModelError, ModelInstallationError) as error:
            raise _translate(error) from None
        return Response(status_code=204)

    router.add_api_route("", create, methods=["POST"], status_code=201)
    router.add_api_route("/{upload_id}/files/{index}", write, methods=["PUT"])
    router.add_api_route("/{upload_id}/preview", preview, methods=["POST"])
    router.add_api_route("/{upload_id}", discard, methods=["DELETE"])
    return router
