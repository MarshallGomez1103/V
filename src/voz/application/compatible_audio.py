"""Local compatible audio through existing persistent jobs and shared runners.

Imported originals, projects, transcripts and synthesis results remain in normal
V history, including on disconnect or timeout. Cancellation does not erase them.
Call from a transport worker thread; runner inference owns the compute slot.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import BinaryIO
from uuid import UUID

from voz.application.create_transcription_job import (
    MAX_PROMPT_CHARS,
    CreateJobError,
    CreateTranscriptionJob,
)
from voz.application.get_transcription_options import (
    TranscriptionOption,
    option_identity,
)
from voz.application.import_media import ImportMedia
from voz.application.job_runner import JobRunner, transcript_id_for
from voz.application.ports.compatible_audio import (
    CompatibleAudioError,
    CompatibleModel,
    CompatibleSpeech,
    CompatibleTranscript,
    CompatibleTranscription,
)
from voz.application.ports.repositories import SegmentRepository, TranscriptRepository
from voz.application.ports.speech_synthesis import SynthesisLocality
from voz.application.ports.synthesis_audio_storage import SynthesisAudioStorage
from voz.application.ports.transcription import TranscriptionSegment, TranscriptionWord
from voz.application.ports.transcription_options import InstallationStatus
from voz.application.projects import CreateProject
from voz.application.synthesis.create_synthesis_job import CreateSynthesisJob
from voz.application.synthesis.errors import SynthesisJobError, SynthesisJobFailureCode
from voz.application.synthesis.runner import SynthesisRunner
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.synthesis_job import SynthesisJob
from voz.domain.entities.synthesis_request import (
    MAX_SYNTHESIS_SPEED,
    MAX_SYNTHESIS_TEXT_CHARS,
    MIN_SYNTHESIS_SPEED,
)
from voz.domain.entities.transcription_job import TranscriptionJob

_POLL_SECONDS = 0.05
_LANGUAGE = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", re.ASCII)
_FAILED = "Audio processing could not be completed."
_MODEL = "The requested local model is not installed or available."
_CANCELLED = "The audio request was cancelled."
_TIMEOUT = "The audio request exceeded its deadline."
Job = TranscriptionJob | SynthesisJob


@dataclass(frozen=True, slots=True)
class LocalCompatibleAudioService:
    create_project: CreateProject
    import_media: ImportMedia
    create_transcription: CreateTranscriptionJob
    transcription_runner: JobRunner
    create_synthesis: CreateSynthesisJob
    synthesis_runner: SynthesisRunner
    transcripts: TranscriptRepository
    segments: SegmentRepository
    synthesis_storage: SynthesisAudioStorage
    timeout_seconds: float = 300.0
    monotonic: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        if (
            isinstance(self.timeout_seconds, bool)
            or not math.isfinite(self.timeout_seconds)
            or not 0 < self.timeout_seconds <= 300
        ):
            raise ValueError(
                "Audio request timeout must be finite and at most 300 seconds."
            )

    def _transcription_models(self) -> dict[str, TranscriptionOption]:
        registrations = self.create_transcription.options.catalog.list_models()
        allowed = {
            option_identity(item.descriptor)
            for item in registrations
            if not item.cloud
            and not item.remote
            and item.files_available
            and item.installation_status is InstallationStatus.REGISTERED
        }
        return {
            f"{option.provider_id}:{option.model_id}": option
            for option in self.create_transcription.options.execute().options
            if option.option_id in allowed
            and not option.cloud
            and option.can_start
            and option.execution is not None
            and ModelCapability.TRANSCRIPTION in option.capabilities
        }

    def _synthesis_models(self) -> dict[str, ModelDescriptor]:
        models: dict[str, ModelDescriptor] = {}
        for registration in self.create_synthesis.catalog.list_models():
            model = registration.descriptor
            if (
                registration.cloud
                or registration.remote
                or not registration.files_available
                or registration.installation_status is not InstallationStatus.REGISTERED
                or not model.supports(ModelCapability.SYNTHESIS)
            ):
                continue
            try:
                provider = self.create_synthesis.providers.get(model.provider_id)
                if (
                    provider.describe().locality is SynthesisLocality.LOCAL
                    and provider.requirements(model).runtime_ready
                    and provider.voices(model)
                ):
                    models[f"{model.provider_id}:{model.model_id}"] = model
            except Exception:
                # Unavailable metadata cannot make a local model startable.
                continue
        return models

    def models(self) -> tuple[CompatibleModel, ...]:
        try:
            models: dict[str, CompatibleModel] = {}
            for key, option in self._transcription_models().items():
                models[key] = CompatibleModel(
                    key, option.provider_id, ("transcription",)
                )
            for key, descriptor in self._synthesis_models().items():
                capabilities = models[key].capabilities if key in models else ()
                models[key] = CompatibleModel(
                    key, descriptor.provider_id, (*capabilities, "synthesis")
                )
            return tuple(models[key] for key in sorted(models))
        except Exception:
            raise CompatibleAudioError(
                "audio_service_unavailable", "Local audio models are unavailable.", 503
            ) from None

    def _guard(self, deadline: float, cancelled: Callable[[], bool]) -> None:
        if cancelled():
            raise CompatibleAudioError("request_cancelled", _CANCELLED, 499)
        if self.monotonic() >= deadline:
            raise CompatibleAudioError("request_timeout", _TIMEOUT, 504)

    def _wait(
        self,
        job_id: UUID,
        get_job: Callable[[UUID], Job | None],
        deadline: float,
        cancelled: Callable[[], bool],
    ) -> Job:
        while True:
            self._guard(deadline, cancelled)
            job = get_job(job_id)
            self._guard(deadline, cancelled)
            if job is None:
                raise CompatibleAudioError("audio_processing_failed", _FAILED, 500)
            if job.state.is_terminal:
                if job.state.value == "COMPLETED":
                    return job
                if job.state.value == "CANCELLED":
                    raise CompatibleAudioError("request_cancelled", _CANCELLED, 499)
                raise CompatibleAudioError("audio_processing_failed", _FAILED, 500)
            self.sleep(min(_POLL_SECONDS, max(0.0, deadline - self.monotonic())))

    @staticmethod
    def _cancel_owned(
        job_id: UUID | None,
        runner: JobRunner | SynthesisRunner,
        get_job: Callable[[UUID], Job | None],
    ) -> None:
        if job_id is None:
            return
        try:
            job = get_job(job_id)
            if job is not None and job.state.is_terminal:
                return
        except Exception:
            pass  # Still request cancellation of our own job after a read outage.
        with suppress(Exception):
            runner.cancel(job_id)

    def transcribe(
        self, request: CompatibleTranscription, *, cancelled: Callable[[], bool]
    ) -> CompatibleTranscript:
        owned: UUID | None = None
        try:
            deadline = self.monotonic() + self.timeout_seconds
            self._guard(deadline, cancelled)
            option = self._transcription_models().get(request.model)
            if option is None:
                raise CompatibleAudioError("model_not_found", _MODEL, 404, "model")
            if (
                request.prompt is not None
                and len(request.prompt.strip()) > MAX_PROMPT_CHARS
            ):
                raise CompatibleAudioError(
                    "invalid_request",
                    "The transcription prompt is too long.",
                    400,
                    "prompt",
                )
            if (
                request.language is not None
                and _LANGUAGE.fullmatch(request.language) is None
            ):
                raise CompatibleAudioError(
                    "invalid_request", "The language tag is invalid.", 400, "language"
                )
            self._guard(deadline, cancelled)
            project = self.create_project.execute(name="Compatible audio")
            self._guard(deadline, cancelled)
            imported = self.import_media.execute(
                source=request.source, project_id=project.id
            )
            self._guard(deadline, cancelled)
            created = self.create_transcription.execute(
                project_id=project.id,
                media_asset_id=imported.media_asset.id,
                option_id=option.option_id,
                language=request.language,
                prompt=request.prompt,
            )
            owned = created.job.id
            self._guard(deadline, cancelled)
            self.transcription_runner.enqueue(owned)
            self._wait(owned, self.create_transcription.jobs.get, deadline, cancelled)
            result = self._transcript(owned, imported.media_asset.id)
            self._guard(deadline, cancelled)
            return result
        except Exception as error:
            self._cancel_owned(
                owned, self.transcription_runner, self.create_transcription.jobs.get
            )
            if isinstance(error, CompatibleAudioError):
                raise
            if isinstance(error, CreateJobError):
                raise CompatibleAudioError(
                    "model_not_found", _MODEL, 409, "model"
                ) from None
            raise CompatibleAudioError(
                "audio_processing_failed", _FAILED, 500
            ) from None

    def _transcript(self, job_id: UUID, media_id: UUID) -> CompatibleTranscript:
        transcript = self.transcripts.get(transcript_id_for(job_id))
        media = self.create_transcription.media_assets.get(media_id)
        if transcript is None or media is None or media.duration_ms is None:
            raise CompatibleAudioError("audio_processing_failed", _FAILED, 500)
        segments = tuple(
            TranscriptionSegment(
                segment.start_ms,
                segment.end_ms,
                segment.text,
                words=tuple(
                    TranscriptionWord(word.start_ms, word.end_ms, word.text)
                    for word in segment.words
                ),
                speaker=str(segment.speaker_id)
                if segment.speaker_id is not None
                else None,
                avg_logprob=segment.avg_logprob,
            )
            for segment in sorted(
                self.segments.list_by_transcript(transcript.id),
                key=lambda segment: (segment.start_ms, segment.end_ms, str(segment.id)),
            )
        )
        return CompatibleTranscript(
            " ".join(segment.text for segment in segments),
            transcript.language,
            media.duration_ms / 1000,
            segments,
        )

    def speech(
        self, request: CompatibleSpeech, *, cancelled: Callable[[], bool]
    ) -> BinaryIO:
        owned: UUID | None = None
        try:
            deadline = self.monotonic() + self.timeout_seconds
            self._guard(deadline, cancelled)
            model = self._synthesis_models().get(request.model)
            if model is None:
                raise CompatibleAudioError("model_not_found", _MODEL, 404, "model")
            if (
                isinstance(request.speed, bool)
                or not math.isfinite(request.speed)
                or not MIN_SYNTHESIS_SPEED <= request.speed <= MAX_SYNTHESIS_SPEED
            ):
                raise CompatibleAudioError(
                    "invalid_request", "The speech speed is invalid.", 400, "speed"
                )
            if (
                not request.input.strip()
                or len(request.input.strip()) > MAX_SYNTHESIS_TEXT_CHARS
                or "\x00" in request.input
            ):
                raise CompatibleAudioError(
                    "invalid_request", "The speech input is invalid.", 400, "input"
                )
            self._guard(deadline, cancelled)
            created = self.create_synthesis.execute(
                text=request.input,
                provider_id=model.provider_id,
                model_id=model.model_id,
                voice_id=request.voice,
                speed=request.speed,
            )
            if not created.reused:
                owned = created.job.id
                self._guard(deadline, cancelled)
                self.synthesis_runner.enqueue(owned)
            self._wait(
                created.job.id, self.create_synthesis.jobs.get, deadline, cancelled
            )
            audio = self.create_synthesis.audio.get_by_job(created.job.id)
            if audio is None:
                raise CompatibleAudioError("audio_processing_failed", _FAILED, 500)
            self._guard(deadline, cancelled)
            handle = self.synthesis_storage.open_for_reading(audio.relative_path)
            try:
                self._guard(deadline, cancelled)
            except Exception:
                handle.close()
                raise
            return handle
        except Exception as error:
            self._cancel_owned(
                owned, self.synthesis_runner, self.create_synthesis.jobs.get
            )
            if isinstance(error, CompatibleAudioError):
                raise
            if isinstance(error, SynthesisJobError):
                if error.code is SynthesisJobFailureCode.VOICE_NOT_FOUND:
                    raise CompatibleAudioError(
                        "invalid_voice",
                        "The selected local voice is unavailable.",
                        400,
                        "voice",
                    ) from None
                if error.code is SynthesisJobFailureCode.REQUEST_INVALID:
                    raise CompatibleAudioError(
                        "invalid_request", "The speech input is invalid.", 400, "input"
                    ) from None
                raise CompatibleAudioError(
                    "model_not_found", _MODEL, 409, "model"
                ) from None
            raise CompatibleAudioError(
                "audio_processing_failed", _FAILED, 500
            ) from None
