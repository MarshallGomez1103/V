"""Create a queued synthesis job, or reuse an identical earlier result."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from voz.application.admission import AdmissionGate
from voz.application.ports.speech_synthesis import (
    SpeechSynthesisProvider,
    SynthesisError,
    SynthesisFailureCode,
)
from voz.application.ports.synthesis_repositories import (
    SynthesisJobRepository,
    SynthesizedAudioRepository,
)
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
)
from voz.application.synthesis.errors import SynthesisJobError, SynthesisJobFailureCode
from voz.application.synthesis_provider_registry import (
    SynthesisProviderNotFoundError,
    SynthesisProviderRegistry,
)
from voz.application.text_chunking import plan_text_chunks
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.synthesis_job import SynthesisJob, SynthesisJobState
from voz.domain.entities.synthesis_request import (
    SynthesisOutputFormat,
    SynthesisRequest,
)
from voz.domain.entities.synthesized_audio import SynthesizedAudio

# ponytail: reuse is found by scanning the newest jobs because the repository
# port has no lookup by request hash. Ceiling: results older than this many jobs
# are re-synthesized instead of reused. A later persistence slice should add a
# nullable indexed `request_hash` column to `synthesis_jobs` and a
# `find_completed_by_hash` method, then this scan can go.
REUSE_SCAN_LIMIT = 500


class SynthesisModelCatalog(Protocol):
    """Registered models; the transcription catalog satisfies it structurally."""

    def list_models(self) -> tuple[ModelRegistration, ...]: ...


def request_hash(request: SynthesisRequest) -> str:
    """Stable identity of what would be rendered: same hash, same audio."""
    payload = json.dumps(
        [
            request.provider_id,
            request.model_id,
            request.model_revision,
            request.voice_id,
            request.speed,
            request.language,
            request.output_format.value,
            request.text,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class CreatedSynthesis:
    """Outcome of :meth:`CreateSynthesisJob.execute`.

    ``reused`` is true when no job was created: ``job`` is an earlier COMPLETED
    one (with its ``audio``) or an identical job that is still in progress
    (``audio`` is ``None``).
    """

    job: SynthesisJob
    audio: SynthesizedAudio | None = None
    reused: bool = False


@dataclass(slots=True)
class CreateSynthesisJob:
    """Revalidate provider, model and voice, chunk the text, then persist."""

    providers: SynthesisProviderRegistry
    catalog: SynthesisModelCatalog
    jobs: SynthesisJobRepository
    audio: SynthesizedAudioRepository
    id_factory: Callable[[], UUID] = uuid4
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    admission: AdmissionGate = field(default_factory=AdmissionGate)
    """Shared with deletion; the default is a private gate."""

    def execute(
        self,
        *,
        text: str,
        provider_id: str,
        model_id: str,
        voice_id: str,
        language: str | None = None,
        speed: float = 1.0,
        output_format: SynthesisOutputFormat = SynthesisOutputFormat.WAV_PCM16_MONO,
    ) -> CreatedSynthesis:
        """Validate and persist under the admission gate, so duplicates collapse."""
        provider = self._provider(provider_id)
        model = self._model(provider_id, model_id)
        self._check_voice(provider, model, voice_id)
        try:
            request = SynthesisRequest(
                text=text,
                provider_id=provider_id,
                model_id=model_id,
                voice_id=voice_id,
                model_revision=model.revision,
                language=language,
                speed=speed,
                output_format=output_format,
            )
        except (TypeError, ValueError) as error:
            raise SynthesisJobError(
                SynthesisJobFailureCode.REQUEST_INVALID, str(error)
            ) from error
        chunks = plan_text_chunks(
            request.text, max_chars=provider.describe().max_chunk_chars
        )
        if not chunks:  # unreachable while the request rejects blank text
            raise SynthesisJobError(
                SynthesisJobFailureCode.REQUEST_INVALID,
                "The text has nothing to synthesize.",
            )
        with self.admission.hold():
            existing = self._find_existing(request)
            if existing is not None:
                return existing
            job = SynthesisJob.create(
                job_id=self.id_factory(),
                request=request,
                chunks_total=len(chunks),
                now=self.clock(),
            )
            self.jobs.add(job)
            return CreatedSynthesis(job)

    def _find_existing(self, request: SynthesisRequest) -> CreatedSynthesis | None:
        wanted = request_hash(request)
        in_progress: SynthesisJob | None = None
        for job in self.jobs.list_recent(REUSE_SCAN_LIMIT):  # newest first
            if request_hash(job.request) != wanted:
                continue
            if job.state is SynthesisJobState.COMPLETED:
                stored = self.audio.get_by_job(job.id)
                if stored is not None:
                    return CreatedSynthesis(job, stored, reused=True)
            elif job.state.is_processable and in_progress is None:
                in_progress = job
        return (
            None if in_progress is None else CreatedSynthesis(in_progress, None, True)
        )

    def _provider(self, provider_id: str) -> SpeechSynthesisProvider:
        try:
            return self.providers.get(provider_id)
        except SynthesisProviderNotFoundError:
            raise SynthesisJobError(
                SynthesisJobFailureCode.PROVIDER_NOT_FOUND,
                "The speech synthesis engine is not known.",
            ) from None

    def _model(self, provider_id: str, model_id: str) -> ModelDescriptor:
        registration = next(
            (
                item
                for item in self.catalog.list_models()
                if item.descriptor.identity == (provider_id, model_id)
                and item.descriptor.supports(ModelCapability.SYNTHESIS)
            ),
            None,
        )
        if registration is None:
            raise SynthesisJobError(
                SynthesisJobFailureCode.MODEL_UNKNOWN,
                "The speech synthesis model is not known.",
            )
        if (
            registration.installation_status is not InstallationStatus.REGISTERED
            or not registration.files_available
        ):
            raise SynthesisJobError(
                SynthesisJobFailureCode.MODEL_NOT_INSTALLED,
                "The speech synthesis model is not installed.",
            )
        return registration.descriptor

    def _check_voice(
        self, provider: SpeechSynthesisProvider, model: ModelDescriptor, voice_id: str
    ) -> None:
        try:
            if not provider.requirements(model).runtime_ready:
                raise SynthesisJobError(
                    SynthesisJobFailureCode.RUNTIME_UNAVAILABLE,
                    "The speech synthesis runtime is not ready.",
                )
            voices = provider.voices(model)
        except SynthesisError as error:
            code = (
                SynthesisJobFailureCode.MODEL_NOT_INSTALLED
                if error.code is SynthesisFailureCode.MODEL_NOT_INSTALLED
                else SynthesisJobFailureCode.RUNTIME_UNAVAILABLE
            )
            raise SynthesisJobError(code, error.user_message) from error
        if all(voice.id != voice_id for voice in voices):
            raise SynthesisJobError(
                SynthesisJobFailureCode.VOICE_NOT_FOUND,
                "The selected voice does not exist in this model.",
            )


__all__ = [
    "REUSE_SCAN_LIMIT",
    "CreateSynthesisJob",
    "CreatedSynthesis",
    "SynthesisModelCatalog",
    "request_hash",
]
