"""JobRunner over a real WAV derivative, a fake provider and SQLite persistence."""

from __future__ import annotations

import math
import shutil
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine

from voz.application.job_runner import (
    JobNotFound,
    JobRunner,
    JobTerminal,
    transcript_id_for,
)
from voz.application.ports.media_normalization import (
    MediaNormalizationCancellationToken,
)
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
    TranscriptionResult,
    TranscriptionSegment,
)
from voz.application.ports.transcription_checkpoint import TranscriptionCheckpoint
from voz.application.ports.transcription_job_selection import JobSelection
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.project import Project
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.infrastructure.inference_audio import FileSystemInferenceAudioSource
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteSegmentRepository,
    SqliteTranscriptionJobRepository,
    SqliteTranscriptRepository,
)
from voz.infrastructure.persistence.schema import metadata
from voz.infrastructure.persistence.transcription_checkpoints import (
    SqliteTranscriptionCheckpointStore,
)
from voz.infrastructure.persistence.transcription_job_selections import (
    SqliteTranscriptionJobSelectionRepository,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
WAV_FIXTURE = REPOSITORY_ROOT / "tests/fixtures/media/synthetic-tone.wav"
BASE_TIME = datetime(2026, 9, 21, 12, tzinfo=UTC)
DESCRIPTOR = ModelDescriptor(
    provider_id="fake-asr",
    model_id="fixture",
    display_name="Fixture",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    source="example/fake-asr",
    revision="f" * 40,
)


class Provider:
    """Deterministic provider: one segment covering each received PCM clip."""

    provider_id = "fake-asr"

    def __init__(
        self,
        *,
        fail_on_call: int | None = None,
        cancel_on_call: int | None = None,
    ) -> None:
        self.calls = 0
        self.fail_on_call = fail_on_call
        self.cancel_on_call = cancel_on_call
        self.on_cancel: Callable[[], object] | None = None
        self.clip_durations_ms: list[int] = []

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        del cancellation
        assert options.model == DESCRIPTOR
        assert options.clip is None
        with wave.open(audio, "rb") as source:
            duration_ms = source.getnframes() * 1_000 // source.getframerate()
        self.calls += 1
        self.clip_durations_ms.append(duration_ms)
        if self.fail_on_call == self.calls:
            raise TranscriptionError(
                TranscriptionFailureCode.PROVIDER_FAILED, "/private/engine crashed"
            )
        if self.cancel_on_call == self.calls and self.on_cancel is not None:
            self.on_cancel()
        return TranscriptionResult(
            (TranscriptionSegment(0, duration_ms, f"chunk-{self.calls}"),),
            "es",
        )


@dataclass(slots=True)
class Preparer:
    storage_root: Path
    calls: list[tuple[UUID, UUID]] = field(default_factory=list[tuple[UUID, UUID]])

    def prepare(
        self,
        *,
        project_id: UUID,
        media_asset_id: UUID,
        cancellation: MediaNormalizationCancellationToken | None = None,
    ) -> None:
        del cancellation
        self.calls.append((project_id, media_asset_id))
        _install_derivative(self.storage_root, project_id, media_asset_id)


def _install_derivative(root: Path, project_id: UUID, media_asset_id: UUID) -> None:
    target = root / "projects" / str(project_id) / "derivatives"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(WAV_FIXTURE, target / f"{media_asset_id}.inference.wav")


@dataclass(slots=True)
class Harness:
    root: Path
    engine: Engine
    job: TranscriptionJob
    provider: Provider
    preparer: Preparer
    runner: JobRunner

    @property
    def jobs(self) -> SqliteTranscriptionJobRepository:
        return SqliteTranscriptionJobRepository(self.engine)

    @property
    def checkpoints(self) -> SqliteTranscriptionCheckpointStore:
        return SqliteTranscriptionCheckpointStore(self.engine)

    def persisted(self) -> TranscriptionJob:
        job = self.jobs.get(self.job.id)
        assert job is not None
        return job


def harness(
    tmp_path: Path,
    *,
    provider: Provider | None = None,
    derivative: bool = True,
) -> Harness:
    engine = create_sqlite_engine((tmp_path / "voz.db").absolute())
    metadata.create_all(engine)
    project = Project("Demo", created_at=BASE_TIME)
    SqliteProjectRepository(engine).add(project)
    asset = MediaAsset(project.id, "a" * 64, "tone.wav", 8_044, duration_ms=250)
    SqliteMediaAssetRepository(engine).add(asset)
    job = TranscriptionJob.create(
        job_id=uuid4(),
        project_id=project.id,
        media_asset_id=asset.id,
        now=BASE_TIME,
    )
    SqliteTranscriptionJobRepository(engine).add(job)
    SqliteTranscriptionJobSelectionRepository(engine).add(
        JobSelection(
            job_id=job.id,
            option_id="option-v1-fixture",
            model=DESCRIPTOR,
            execution=None,
            language=None,
            created_at=BASE_TIME,
        )
    )
    root = tmp_path / "data"
    if derivative:
        _install_derivative(root, project.id, asset.id)
    fake_provider = provider or Provider()
    preparer = Preparer(root)
    ticks = iter(range(1, 10_000))
    runner = JobRunner(
        jobs=SqliteTranscriptionJobRepository(engine),
        selections=SqliteTranscriptionJobSelectionRepository(engine),
        media_assets=SqliteMediaAssetRepository(engine),
        transcripts=SqliteTranscriptRepository(engine),
        segments=SqliteSegmentRepository(engine),
        checkpoints=SqliteTranscriptionCheckpointStore(engine),
        provider_for=lambda selection: fake_provider,
        audio_source_for=lambda project_id, media_asset_id: (
            FileSystemInferenceAudioSource(root, project_id, media_asset_id)
        ),
        audio_preparer=preparer,
        clock=lambda: BASE_TIME + timedelta(seconds=next(ticks)),
        chunk_duration_ms=100,
        overlap_ms=20,
    )
    return Harness(root, engine, job, fake_provider, preparer, runner)


def test_job_completes_and_persists_transcript_segments(tmp_path: Path) -> None:
    fixture = harness(tmp_path)

    finished = fixture.runner.run_job(fixture.job.id)

    assert finished is not None
    assert finished.state is TranscriptionJobState.COMPLETED
    assert finished.progress == 1.0
    assert fixture.persisted() == finished
    assert fixture.provider.calls == 3
    assert fixture.preparer.calls == []
    transcript = SqliteTranscriptRepository(fixture.engine).get(
        transcript_id_for(fixture.job.id)
    )
    assert transcript is not None
    assert transcript.language == "es"
    assert transcript.media_asset_id == fixture.job.media_asset_id
    segments = SqliteSegmentRepository(fixture.engine).list_by_transcript(transcript.id)
    assert [(s.start_ms, s.end_ms, s.text) for s in segments] == [
        (0, 100, "chunk-1"),
        (100, 200, "chunk-2"),
        (200, 250, "chunk-3"),
    ]
    fixture.engine.dispose()


def test_missing_derivative_is_prepared_before_transcribing(tmp_path: Path) -> None:
    fixture = harness(tmp_path, derivative=False)

    finished = fixture.runner.run_job(fixture.job.id)

    assert finished is not None
    assert finished.state is TranscriptionJobState.COMPLETED
    assert fixture.preparer.calls == [
        (fixture.job.project_id, fixture.job.media_asset_id)
    ]
    fixture.engine.dispose()


def test_provider_failure_persists_stable_code_not_message(tmp_path: Path) -> None:
    fixture = harness(tmp_path, provider=Provider(fail_on_call=2))

    finished = fixture.runner.run_job(fixture.job.id)

    assert finished is not None
    assert finished.state is TranscriptionJobState.FAILED
    assert finished.error_code == "transcription_provider_failed"
    assert math.isclose(finished.progress, 1 / 3)
    persisted = fixture.persisted()
    assert persisted.error_code == finished.error_code
    assert "/private/" not in (persisted.error_code or "")
    assert len(fixture.checkpoints.list_for_job(fixture.job.id)) == 1
    fixture.engine.dispose()


def test_cancel_mid_transcription_stops_between_chunks(tmp_path: Path) -> None:
    provider = Provider(cancel_on_call=2)
    fixture = harness(tmp_path, provider=provider)
    provider.on_cancel = lambda: fixture.runner.cancel(fixture.job.id)

    finished = fixture.runner.run_job(fixture.job.id)

    assert finished is not None
    assert finished.state is TranscriptionJobState.CANCELLED
    # Chunk 1 stays committed; chunk 2 was in flight and is discarded, not redone.
    assert provider.calls == 2
    assert math.isclose(finished.progress, 1 / 3)
    assert fixture.persisted().state is TranscriptionJobState.CANCELLED
    assert len(fixture.checkpoints.list_for_job(fixture.job.id)) == 1
    assert (
        SqliteTranscriptRepository(fixture.engine).get(
            transcript_id_for(fixture.job.id)
        )
        is None
    )
    assert fixture.runner.run_job(fixture.job.id) == finished
    assert provider.calls == 2
    with pytest.raises(JobTerminal):
        fixture.runner.cancel(fixture.job.id)
    fixture.engine.dispose()


def test_cancel_queued_job_is_immediate_and_skipped_by_worker(
    tmp_path: Path,
) -> None:
    fixture = harness(tmp_path)

    cancelled = fixture.runner.cancel(fixture.job.id)

    assert cancelled.state is TranscriptionJobState.CANCELLED
    assert fixture.runner.run_job(fixture.job.id) == cancelled
    assert fixture.provider.calls == 0
    with pytest.raises(JobNotFound):
        fixture.runner.cancel(uuid4())
    fixture.engine.dispose()


def test_worker_thread_processes_enqueued_job(tmp_path: Path) -> None:
    fixture = harness(tmp_path)
    fixture.runner.start()
    try:
        fixture.runner.enqueue(fixture.job.id)
        assert fixture.runner.wait_idle(10.0)
    finally:
        fixture.runner.stop()
    assert fixture.persisted().state is TranscriptionJobState.COMPLETED
    fixture.engine.dispose()


def test_recover_resumes_transcribing_job_without_repeating_chunk(
    tmp_path: Path,
) -> None:
    fixture = harness(tmp_path)
    jobs = fixture.jobs
    interrupted = (
        fixture.job.transition_to(TranscriptionJobState.PROBING, at=BASE_TIME)
        .transition_to(TranscriptionJobState.PREPROCESSING, at=BASE_TIME)
        .transition_to(TranscriptionJobState.TRANSCRIBING, at=BASE_TIME)
        .with_progress(1 / 3, at=BASE_TIME)
    )
    jobs.save(interrupted)
    fixture.checkpoints.commit(
        TranscriptionCheckpoint(
            job_id=interrupted.id,
            chunk_index=0,
            process_start_ms=0,
            process_end_ms=120,
            owned_start_ms=0,
            owned_end_ms=100,
            provider_id=DESCRIPTOR.provider_id,
            model_id=DESCRIPTOR.model_id,
            model_source=DESCRIPTOR.source,
            model_revision=DESCRIPTOR.revision,
            requested_language=None,
            segments=(TranscriptionSegment(0, 100, "confirmed"),),
            language="es",
            progress=1 / 3,
            job_progress=1 / 3,
            completed_at=BASE_TIME,
        ),
        interrupted,
    )

    assert fixture.runner.recover() == (interrupted.id,)
    assert fixture.runner.run_job(interrupted.id) is not None
    finished = fixture.persisted()

    assert finished.state is TranscriptionJobState.COMPLETED
    assert fixture.provider.calls == 2
    segments = SqliteSegmentRepository(fixture.engine).list_by_transcript(
        transcript_id_for(interrupted.id)
    )
    assert [s.text for s in segments] == ["confirmed", "chunk-1", "chunk-2"]
    assert fixture.runner.recover() == ()
    fixture.engine.dispose()


def test_recover_finishes_job_left_in_cancelling(tmp_path: Path) -> None:
    fixture = harness(tmp_path)
    fixture.jobs.save(
        fixture.job.transition_to(TranscriptionJobState.CANCELLING, at=BASE_TIME)
    )

    fixture.runner.recover()
    finished = fixture.runner.run_job(fixture.job.id)

    assert finished is not None
    assert finished.state is TranscriptionJobState.CANCELLED
    assert fixture.provider.calls == 0
    fixture.engine.dispose()
