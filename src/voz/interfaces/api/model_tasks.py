"""Thin HTTP adapter for background model install tasks."""

from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from voz.application.model_tasks import (
    ModelTaskError,
    ModelTaskFailureCode,
    ModelTaskRunner,
    ModelTaskView,
)

_STATUS = {
    ModelTaskFailureCode.UNCONFIRMED: 400,
    ModelTaskFailureCode.UNKNOWN_MODEL: 404,
    ModelTaskFailureCode.ALREADY_INSTALLED: 409,
    ModelTaskFailureCode.EXTERNAL_NOT_FOUND: 404,
    ModelTaskFailureCode.TASK_NOT_FOUND: 404,
    ModelTaskFailureCode.TASK_TERMINAL: 409,
    ModelTaskFailureCode.FAILED: 503,
}


class InstallRequest(BaseModel):
    method: Literal["download", "import"]
    origin: Literal["buzz"] | None = None  # import only
    confirm: bool = False


class TaskList(BaseModel):
    tasks: list[ModelTaskView]


def create_model_tasks_router(runner: ModelTaskRunner) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["models"])

    def call[T](action: Callable[[], T]) -> T:
        try:
            return action()
        except ModelTaskError as error:
            raise HTTPException(
                status_code=_STATUS[error.code],
                detail={"code": error.code, "message": error.user_message},
            ) from None

    def install(model_id: str, body: InstallRequest) -> ModelTaskView:
        return call(
            lambda: runner.enqueue(
                model_id, body.method, body.origin, confirm=body.confirm
            )
        )

    def list_tasks() -> TaskList:
        return TaskList(tasks=list(runner.list_tasks()))

    def get_task(task_id: str) -> ModelTaskView:
        return call(lambda: runner.get(task_id))

    def cancel_task(task_id: str) -> ModelTaskView:
        return call(lambda: runner.cancel(task_id))

    router.add_api_route(
        "/models/{model_id}/install",
        install,
        methods=["POST"],
        response_model=ModelTaskView,
        status_code=202,
    )
    router.add_api_route(
        "/model-tasks", list_tasks, methods=["GET"], response_model=TaskList
    )
    router.add_api_route(
        "/model-tasks/{task_id}",
        get_task,
        methods=["GET"],
        response_model=ModelTaskView,
    )
    router.add_api_route(
        "/model-tasks/{task_id}/cancel",
        cancel_task,
        methods=["POST"],
        response_model=ModelTaskView,
        status_code=202,
    )
    return router
