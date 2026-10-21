"""Create a queued transcription job with a reproducible selection snapshot."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from voz.application.admission import AdmissionGate
from voz.application.asr_device_selection import ComputeDevice
from voz.application.get_transcription_options import (
    BlockingReason,
    GetTranscriptionOptions,
    TranscriptionOption,
    option_identity,
)
from voz.application.ports.diarization import DiarizationOptions
from voz.application.ports.diarization_availability import DiarizationAvailability
from voz.application.ports.project_glossary import ProjectGlossaryRepository
from voz.application.ports.repositories import (
    MediaAssetRepository,
    ProjectRepository,
    TranscriptionJobRepository,
)
from voz.application.ports.transcription_job_selection import (
    JobSelection,
    JobWithSelectionWriter,
    TranscriptionJobSelectionRepository,
)
from voz.application.quality_profiles import DEFAULT_PROFILE_NAME, get_profile
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
    DIARIZATION_UNAVAILABLE = "diarization_unavailable"
    DIARIZATION_MODELS_MISSING = "diarization_models_missing"
    PROMPT_INVALID = "job_prompt_invalid"
    QUALITY_PROFILE_UNKNOWN = "quality_profile_unknown"
    OPTIONS_UNSUPPORTED = "job_options_unsupported"
    CLOUD_CONSENT_REQUIRED = "cloud_consent_required"


MAX_PROMPT_CHARS = 600


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
    diarization_availability: DiarizationAvailability | None = None
    """``None`` means diarization is not wired, so requesting it is refused."""
    glossaries: ProjectGlossaryRepository | None = None
    """``None`` means no glossary is wired: jobs get an empty one."""
    job_writer: JobWithSelectionWriter | None = None
    """Writes job and selection in one transaction; ``None`` falls back to two."""
    id_factory: Callable[[], UUID] = uuid4
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    admission: AdmissionGate = field(default_factory=AdmissionGate)
    """Shared with project/model deletion; the default is a private gate."""

    def execute(
        self,
        *,
        project_id: UUID,
        media_asset_id: UUID,
        option_id: str,
        language: str | None = None,
        diarization: DiarizationOptions | None = None,
        profile: str | None = None,
        prompt: str | None = None,
        cloud_consent: bool = False,
    ) -> CreatedJob:
        """Validate and persist under the admission gate, so every check holds.

        ``cloud_consent`` must be ``True`` for an option that sends audio off
        this machine; it is ignored for local options.
        """
        with self.admission.hold():
            return self._create(
                project_id=project_id,
                media_asset_id=media_asset_id,
                option_id=option_id,
                language=language,
                diarization=diarization,
                profile=profile,
                prompt=prompt,
                cloud_consent=cloud_consent,
            )

    def _create(
        self,
        *,
        project_id: UUID,
        media_asset_id: UUID,
        option_id: str,
        language: str | None,
        diarization: DiarizationOptions | None,
        profile: str | None,
        prompt: str | None,
        cloud_consent: bool,
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
        prompt = (prompt or "").strip() or None
        if prompt is not None and len(prompt) > MAX_PROMPT_CHARS:
            raise CreateJobError(
                CreateJobFailureCode.PROMPT_INVALID,
                f"The style prompt can have at most {MAX_PROMPT_CHARS} characters.",
            )
        quality_profile = get_profile(profile or DEFAULT_PROFILE_NAME)
        if quality_profile is None:
            raise CreateJobError(
                CreateJobFailureCode.QUALITY_PROFILE_UNKNOWN,
                "The quality profile is not known.",
            )
        option = self._current_option(option_id)
        if option.cloud and cloud_consent is not True:
            raise CreateJobError(
                CreateJobFailureCode.CLOUD_CONSENT_REQUIRED,
                "This option sends the audio to a cloud provider. "
                "Confirm that explicitly to continue.",
            )
        model = self._descriptor_for(option_id)
        glossary = () if self.glossaries is None else self.glossaries.get(project_id)
        if model.provider_id == "sherpa-onnx-asr":
            if profile not in (None, DEFAULT_PROFILE_NAME) or prompt or glossary:
                raise CreateJobError(
                    CreateJobFailureCode.OPTIONS_UNSUPPORTED,
                    "Whisper ONNX does not support decoding profiles, prompts "
                    "or project glossaries.",
                )
            quality_profile = None
        if any(
            job.state.is_processable
            for job in self.jobs.list_by_media_asset(media_asset_id)
        ):
            raise CreateJobError(
                CreateJobFailureCode.JOB_ALREADY_ACTIVE,
                "A transcription job is already active for this media asset.",
            )
        self._check_memory(option, model)
        if diarization is not None:
            self._check_diarization()

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
            diarization=diarization,
            quality_profile=quality_profile,
            glossary=glossary,
            prompt=prompt,
        )
        if self.job_writer is None:
            self.jobs.add(job)
            self.selections.add(selection)
        else:
            self.job_writer.add_with_selection(job, selection)
        return CreatedJob(job, selection)

    def _check_diarization(self) -> None:
        """Refuse before creating anything; missing models are fixable by download."""
        availability = self.diarization_availability
        if availability is None or not availability.runtime_available():
            raise CreateJobError(
                CreateJobFailureCode.DIARIZATION_UNAVAILABLE,
                "Speaker diarization is not available. "
                "Install its runtime, or disable it.",
            )
        if not availability.models_installed():
            raise CreateJobError(
                CreateJobFailureCode.DIARIZATION_MODELS_MISSING,
                "The speaker models are not installed. "
                "Download them in the model manager, or disable speakers.",
            )

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
    "MAX_PROMPT_CHARS",
    "CreateJobError",
    "CreateJobFailureCode",
    "CreateTranscriptionJob",
    "CreatedJob",
]
