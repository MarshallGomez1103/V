"""In-memory ports shared by the synthesis use-case tests."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import UTC, datetime
from typing import BinaryIO
from uuid import UUID

from voz.application.ports.speech_synthesis import PcmAudio
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
)
from voz.application.synthesis.create_synthesis_job import (
    request_hash as hash_request,
)
from voz.domain.entities.synthesis_job import SynthesisJob, SynthesisJobState
from voz.domain.entities.synthesized_audio import SynthesizedAudio
from voz.infrastructure.tts.fake import fake_tts_descriptor

NOW = datetime(2026, 10, 12, 9, tzinfo=UTC)


class MemoryJobs:
    def __init__(self) -> None:
        self.items: dict[UUID, SynthesisJob] = {}

    def add(self, job: SynthesisJob) -> None:
        assert job.id not in self.items
        self.items[job.id] = job

    def save(self, job: SynthesisJob) -> None:
        assert job.id in self.items
        self.items[job.id] = job

    def get(self, job_id: UUID) -> SynthesisJob | None:
        return self.items.get(job_id)

    def list_recent(self, limit: int) -> Sequence[SynthesisJob]:
        newest = sorted(self.items.values(), key=lambda j: j.created_at, reverse=True)
        return newest[:limit]

    def find_by_hash(
        self, request_hash: str, states: Collection[SynthesisJobState]
    ) -> SynthesisJob | None:
        matches = [
            job
            for job in self.items.values()
            if job.state in states and hash_request(job.request) == request_hash
        ]
        return max(matches, key=lambda job: job.created_at, default=None)

    def list_recoverable(self) -> Sequence[SynthesisJob]:
        return [j for j in self.items.values() if not j.state.is_terminal]

    def delete(self, job_id: UUID) -> bool:
        return self.items.pop(job_id, None) is not None


class MemoryAudio:
    def __init__(self) -> None:
        self.items: dict[UUID, SynthesizedAudio] = {}

    def add(self, audio: SynthesizedAudio) -> None:
        self.items[audio.job_id] = audio

    def get_by_job(self, job_id: UUID) -> SynthesizedAudio | None:
        return self.items.get(job_id)

    def delete(self, job_id: UUID) -> None:
        self.items.pop(job_id, None)


class MemoryStorage:
    """Records deletions; the real adapter is tested by its own slice (V3-04)."""

    def __init__(self) -> None:
        self.deleted: list[str] = []

    def write(
        self, job_id: UUID, chunks: Sequence[PcmAudio], gaps_ms: Sequence[int]
    ) -> SynthesizedAudio:
        raise NotImplementedError

    def open_for_reading(self, relative_path: str) -> BinaryIO:
        raise NotImplementedError

    def delete(self, relative_path: str) -> None:
        self.deleted.append(relative_path)

    def delete_job(self, job_id: UUID) -> None:
        self.deleted.append(f"synthesis/{job_id}/audio.wav")


class MemoryCatalog:
    def __init__(self, *registrations: ModelRegistration) -> None:
        self.registrations = registrations

    def list_models(self) -> tuple[ModelRegistration, ...]:
        return self.registrations


def installed_fake_model() -> ModelRegistration:
    return ModelRegistration(
        fake_tts_descriptor(), InstallationStatus.REGISTERED, files_available=True
    )
