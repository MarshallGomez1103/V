"""Preview custom weights, then copy, validate in isolation and publish explicitly."""

from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext

from voz.application.ports.custom_models import (
    CustomModelBackend,
    CustomModelError,
    CustomModelPlan,
    CustomModelPreview,
    CustomModelRequest,
    CustomModelValidator,
)
from voz.application.ports.model_installation import CancelCheck, ProgressCallback
from voz.domain.entities.model_descriptor import ModelDescriptor


class ImportCustomModel:
    def __init__(
        self,
        backend: CustomModelBackend,
        validator: CustomModelValidator,
        *,
        validation_context: Callable[[CancelCheck], AbstractContextManager[None]]
        | None = None,
    ) -> None:
        self._backend = backend
        self._validator = validator
        self._validation_context: Callable[
            [CancelCheck], AbstractContextManager[None]
        ] = validation_context or _unrestricted_validation
        self._plans: dict[str, CustomModelPlan] = {}
        self._lock = threading.Lock()

    def prepare(self, request: CustomModelRequest) -> CustomModelPreview:
        plan = self._backend.prepare(request)
        with self._lock:
            # ponytail: previews are process-local; at most 100 pending choices.
            # Persistent/resumable previews can replace this if sessions need them.
            if len(self._plans) >= 100:
                self._plans.pop(next(iter(self._plans)))
            self._plans[plan.preview.id] = plan
        return plan.preview

    def preview(self, preview_id: str) -> CustomModelPreview:
        with self._lock:
            plan = self._plans.get(preview_id)
        if plan is None:
            raise CustomModelError(
                "custom_model_preview_expired",
                "Prepare the model again before confirming.",
            )
        return plan.preview

    def execute(
        self,
        preview_id: str,
        *,
        confirm: bool,
        progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> ModelDescriptor:
        if confirm is not True:
            raise CustomModelError(
                "model_install_unconfirmed",
                "Installing a model must be confirmed explicitly.",
            )
        with self._lock:
            plan = self._plans.get(preview_id)
        if plan is None:
            raise CustomModelError(
                "custom_model_preview_expired",
                "Prepare the model again before confirming.",
            )
        stopped = cancelled or (lambda: False)
        directory = self._backend.stage(plan, progress=progress, cancelled=stopped)
        try:
            with self._validation_context(stopped):
                if stopped():
                    raise CustomModelError(
                        "model_installation_cancelled", "The import was cancelled."
                    )
                validation = self._validator.validate(
                    directory,
                    plan.preview.descriptor.provider_id,
                    plan.preview.family,
                    file_roles=plan.file_roles,
                    cancelled=stopped,
                )
            descriptor = self._backend.publish(
                plan, directory, validation, cancelled=stopped
            )
        finally:
            self._backend.discard(directory)
        with self._lock:
            self._plans.pop(preview_id, None)
        return descriptor


def _unrestricted_validation(_: CancelCheck) -> AbstractContextManager[None]:
    return nullcontext()
