"""Create a queued transcription job with a reproducible selection snapshot."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from voz.application.asr_device_selection import ComputeDevice
from voz.application.get_transcription_options import (
    BlockingReason,
    GetTranscriptionOptions,
    TranscriptionOption,
    option_identity,
)
from voz.application.ports.repositories import (
    MediaAssetRepository,
    ProjectRepository,
    TranscriptionJobRepository,
)
from voz.application.ports.transcription_job_selection import (
    JobSelection,
    TranscriptionJobSelectionRepository,
)
from voz.application.resource_requirements import find_shortfall
from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.domain.entities.transcription_job import TranscriptionJob


class CreateJobFailureCode(StrEnum):
    """Stable failure codes translated one-to-one by the HTTP adapter."""

    PROJECT_NOT_FOUND = "project_not_found"
    MEDIA_ASSET_NOT_FOUND = "media_asset_not_found"
    OPTION_UNKNOWN = "option_unknown"
    OPTION_NOT_STARTABLE = "option_not_startable"
    JOB_ALREADY_ACTIVE = "job_already_active"
    INSUFFICIENT_VRAM = "insufficient_vram"
    INSUFFICIENT_RAM = "insufficient_ram"


class CreateJobError(RuntimeError):
    """Typed creation failure with a user-safe message."""

    def __init__(
        self,
        code: CreateJobFailureCode,
        user_message: str,
        *,
        blocking_reasons: tuple[BlockingReason, ...] = (),
        required_mib: int | None = None,
        available_mib: int | None = None,
    ) -> None:
        self.code = code
        self.user_message = user_message
        self.blocking_reasons = blocking_reasons
        self.required_mib = required_mib
        self.available_mib = available_mib
        super().__init__(user_message)


@dataclass(frozen=True, slots=True)
class CreatedJob:
    job: TranscriptionJob
    selection: JobSelection


@dataclass(slots=True)
class CreateTranscriptionJob:
    """Revalidate the option against the live catalog, then persist job + snapshot."""

    options: GetTranscriptionOptions
    projects: ProjectRepository
    media_assets: MediaAssetRepository
    jobs: TranscriptionJobRepository
    selections: TranscriptionJobSelectionRepository
    id_factory: Callable[[], UUID] = uuid4
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def execute(
        self,
        *,
        project_id: UUID,
        media_asset_id: UUID,
        option_id: str,
        language: str | None = None,
    ) -> CreatedJob:
        if self.projects.get(project_id) is None:
            raise CreateJobError(
                CreateJobFailureCode.PROJECT_NOT_FOUND,
                "The project does not exist.",
            )
        media_asset = self.media_assets.get(media_asset_id)
        if media_asset is None or media_asset.project_id != project_id:
            raise CreateJobError(
                CreateJobFailureCode.MEDIA_ASSET_NOT_FOUND,
                "The media asset does not exist in this project.",
            )
        option = self._current_option(option_id)
        model = self._descriptor_for(option_id)
        if any(
            job.state.is_processable
            for job in self.jobs.list_by_media_asset(media_asset_id)
        ):
            raise CreateJobError(
                CreateJobFailureCode.JOB_ALREADY_ACTIVE,
                "A transcription job is already active for this media asset.",
            )
        self._check_memory(option, model)

        now = self.clock()
        job = TranscriptionJob.create(
            job_id=self.id_factory(),
            project_id=project_id,
            media_asset_id=media_asset_id,
            now=now,
        )
        selection = JobSelection(
            job_id=job.id,
            option_id=option.option_id,
            model=model,
            execution=option.execution,
            language=language,
            created_at=now,
        )
        self.jobs.add(job)
        self.selections.add(selection)
        return CreatedJob(job, selection)

    def _check_memory(
        self, option: TranscriptionOption, model: ModelDescriptor
    ) -> None:
        """S14.05/S14.06: refuse a load that measured free memory cannot hold.

        Unmeasured memory never blocks: the estimate is advisory, not a proof.
        """
        if option.execution is None:
            return
        hardware = self.options.runtime.probe(model.provider_id).hardware
        if hardware is None:
            return
        shortfall = find_shortfall(model.model_id, option.execution, hardware)
        if shortfall is None:
            return
        if shortfall.device is ComputeDevice.CUDA:
            code = CreateJobFailureCode.INSUFFICIENT_VRAM
            message = (
                "Not enough free GPU memory to load this model. "
                "Choose a smaller model or use the CPU."
            )
        else:
            code = CreateJobFailureCode.INSUFFICIENT_RAM
            message = (
                "Not enough free RAM to load this model. "
                "Choose a smaller model or free some memory."
            )
        raise CreateJobError(
            code,
            message,
            required_mib=shortfall.required_mib,
            available_mib=shortfall.available_mib,
        )

    def _current_option(self, option_id: str) -> TranscriptionOption:
        option = next(
            (
                item
                for item in self.options.execute().options
                if item.option_id == option_id
            ),
            None,
        )
        if option is None:
            raise CreateJobError(
                CreateJobFailureCode.OPTION_UNKNOWN,
                "The transcription option is not known.",
            )
        if not option.can_start:
            raise CreateJobError(
                CreateJobFailureCode.OPTION_NOT_STARTABLE,
                "The transcription option cannot start right now.",
                blocking_reasons=option.blocking_reasons,
            )
        return option

    def _descriptor_for(self, option_id: str) -> ModelDescriptor:
        # The option projection intersects capabilities with the runtime, so the
        # exact descriptor is re-read from the catalog behind the same query.
        for registration in self.options.catalog.list_models():
            if option_identity(registration.descriptor) == option_id:
                return registration.descriptor
        raise CreateJobError(
            CreateJobFailureCode.OPTION_UNKNOWN,
            "The transcription option is not known.",
        )


__all__ = [
    "CreateJobError",
    "CreateJobFailureCode",
    "CreateTranscriptionJob",
    "CreatedJob",
]
