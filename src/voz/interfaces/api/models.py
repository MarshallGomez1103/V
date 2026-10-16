"""Thin HTTP adapter for the local model manager."""

from collections.abc import Callable, Coroutine
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from voz.application.import_custom_model import ImportCustomModel
from voz.application.model_manager import (
    ListModels,
    ModelList,
    ModelManagementError,
    ModelManagementFailureCode,
    RemovedModel,
    RemoveModel,
)
from voz.application.ports.custom_models import (
    CustomModelError,
    CustomModelPreview,
    CustomModelRequest,
)
from voz.interfaces.api.errors import api_error

_STATUS = {
    ModelManagementFailureCode.DELETE_UNCONFIRMED: 400,
    ModelManagementFailureCode.NOT_INSTALLED: 404,
    ModelManagementFailureCode.IN_USE: 409,
    ModelManagementFailureCode.REMOVE_FAILED: 500,
}


class PrivateModelRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def guarded(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError:
                raise api_error(
                    422, "custom_model_invalid", "The model request is not valid."
                ) from None

        return guarded


class CustomPreviewRequest(BaseModel):
    source_type: Literal["folder", "url", "huggingface"]
    source: str = Field(max_length=2048)
    engine: str = Field(max_length=64)
    family: str = Field(max_length=64)
    display_name: str = Field(max_length=128)
    license: str = Field(default="unknown", max_length=512)
    revision: str = Field(default="main", max_length=255)
    file_roles: dict[str, str] = Field(default_factory=dict[str, str], max_length=32)


def custom_model_error(error: CustomModelError) -> Exception:
    status = 404 if error.code == "custom_model_preview_expired" else 422
    return api_error(status, error.code, error.user_message)


def create_models_router(
    list_models: ListModels,
    remove_model: RemoveModel,
    *,
    custom: ImportCustomModel | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["models"], route_class=PrivateModelRoute)

    def preview_custom(body: CustomPreviewRequest) -> CustomModelPreview:
        if custom is None:
            raise api_error(
                503,
                "custom_model_unavailable",
                "Custom model imports are not available.",
            )
        try:
            return custom.prepare(CustomModelRequest(**body.model_dump()))
        except CustomModelError as error:
            raise custom_model_error(error) from None

    router.add_api_route(
        "/models/custom/preview",
        preview_custom,
        methods=["POST"],
        response_model=CustomModelPreview,
    )

    def get_models() -> ModelList:
        return list_models.execute()

    def delete_model(model_id: str, confirm: str | None = None) -> RemovedModel:
        try:
            return remove_model.execute(model_id, confirm)
        except ModelManagementError as error:
            raise HTTPException(
                status_code=_STATUS[error.code],
                detail={"code": error.code, "message": error.user_message},
            ) from None

    router.add_api_route(
        "/models", get_models, methods=["GET"], response_model=ModelList
    )
    router.add_api_route(
        "/models/{model_id}",
        delete_model,
        methods=["DELETE"],
        response_model=RemovedModel,
    )
    return router
