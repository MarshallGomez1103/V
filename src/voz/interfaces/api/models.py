"""Thin HTTP adapter for the local model manager."""

from fastapi import APIRouter, HTTPException

from voz.application.model_manager import (
    ListModels,
    ModelList,
    ModelManagementError,
    ModelManagementFailureCode,
    RemovedModel,
    RemoveModel,
)

_STATUS = {
    ModelManagementFailureCode.DELETE_UNCONFIRMED: 400,
    ModelManagementFailureCode.NOT_INSTALLED: 404,
    ModelManagementFailureCode.IN_USE: 409,
    ModelManagementFailureCode.REMOVE_FAILED: 500,
}


def create_models_router(
    list_models: ListModels, remove_model: RemoveModel
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["models"])

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
