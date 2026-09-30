"""JobRunner over a real WAV derivative, a fake provider and SQLite persistence."""

from __future__ import annotations

import hashlib
import math
import shutil
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from io import BytesIO
from itertools import pairwise
from pathlib import Path
from typing import BinaryIO, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine

from voz.application.job_runner import (
    InferenceAudioPreparer,
    JobNotFound,
    JobRunner,
    JobTerminal,
    transcript_id_for,
)
from voz.application.normalize_media import NormalizeImportedMedia
from voz.application.ports.disk_space import DiskLocation
from voz.application.ports.media_normalization import (
    MediaNormalizationCancellationToken,
    MediaNormalizationPort,
    NormalizedAudio,
)
from voz.application.ports.media_probe import (
    MediaProbeResult,
    MediaStreamKind,
    ProbedMediaStream,
)
from voz.application.ports.media_storage import MediaStoragePort
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
    TranscriptionResult,
    TranscriptionSegment,
    TranscriptionWord,
)
from voz.application.ports.transcription_checkpoint import TranscriptionCheckpoint
from voz.application.ports.transcription_job_selection import JobSelection
from voz.application.prepare_inference_audio import PrepareInferenceAudio
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.project import Project
from voz.domain.entities.segment import Segment
from voz.domain.entities.transcript import Transcript
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
        crash_on_call: int | None = None,
        content_text: bool = False,
    ) -> None:
        self.calls = 0
        self.crash_on_call = crash_on_call
        self.content_text = content_text
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
            frames = source.readframes(source.getnframes())
        self.calls += 1
        if self.crash_on_call == self.calls:
            raise Crash
        self.clip_durations_ms.append(duration_ms)
        if self.fail_on_call == self.calls:
            raise TranscriptionError(
                TranscriptionFailureCode.PROVIDER_FAILED, "/private/engine crashed"
            )
        if self.cancel_on_call == self.calls and self.on_cancel is not None:
            self.on_cancel()
        return TranscriptionResult(
            (TranscriptionSegment(0, duration_ms, self._text(frames)),),
            "es",
        )

    def _text(self, frames: bytes) -> str:
        # Depends on the clip, not on how many times the provider was called.
        if self.content_text:
            return "clip-" + hashlib.sha256(frames).hexdigest()[:8]
        return f"chunk-{self.calls}"


class Crash(BaseException):
    """Simulates a process kill: not an ``Exception``, so nothing records FAILED."""


@dataclass(slots=True)
class Preparer:
    storage_root: Path
    calls: list[tuple[UUID, UUID]] = field(default_factory=list[tuple[UUID, UUID]])
    crash_first: bool = False

    def prepare(
        self,
        *,
        project_id: UUID,
        media_asset_id: UUID,
        cancellation: MediaNormalizationCancellationToken | None = None,
    ) -> None:
        del cancellation
        self.calls.append((project_id, media_asset_id))
        if self.crash_first:
            self.crash_first = False
            raise Crash
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
    audio_preparer: InferenceAudioPreparer | None = None,
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
        audio_preparer=audio_preparer or preparer,
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


# -- disk space (S14.03) -------------------------------------------------------


class _LowDisk:
    def free_bytes(self, location: DiskLocation) -> int:
        return 1024


class _Storage:
    def open_original(self, *, project_id: UUID, media_asset_id: UUID) -> BinaryIO:
        return BytesIO(b"original")

    def import_original(self, **_: object) -> object:
        raise NotImplementedError

    def discard_original(self, **_: object) -> None:
        raise NotImplementedError


class _Probe:
    def probe(self, source: BinaryIO) -> MediaProbeResult:
        stream = ProbedMediaStream(
            0, MediaStreamKind.AUDIO, "pcm_s16le", True, 8_000, 1
        )
        return MediaProbeResult(("wav",), (stream,), 250)


class _NeverNormalizes:
    def normalize(self, **_: object) -> NormalizedAudio:
        raise AssertionError("must not start normalizing without disk space")


def test_job_fails_with_disk_space_code_and_leaves_no_partial_artifacts(
    tmp_path: Path,
) -> None:
    fixture = harness(tmp_path, derivative=False)
    media_assets = SqliteMediaAssetRepository(fixture.engine)
    fixture.runner.audio_preparer = PrepareInferenceAudio(
        media_storage=cast(MediaStoragePort, _Storage()),
        media_probe=_Probe(),
        media_assets=media_assets,
        normalize=NormalizeImportedMedia(
            media_storage=cast(MediaStoragePort, _Storage()),
            media_normalization=cast(MediaNormalizationPort, _NeverNormalizes()),
            disk_space=_LowDisk(),
        ),
    )

    finished = fixture.runner.run_job(fixture.job.id)

    assert finished is not None
    assert finished.state is TranscriptionJobState.FAILED
    assert finished.error_code == "disk_space_insufficient"
    assert fixture.persisted().error_code == "disk_space_insufficient"
    assert fixture.provider.calls == 0
    assert not (fixture.root / "projects").exists()
    assert fixture.checkpoints.list_for_job(fixture.job.id) == ()
    assert (
        SqliteTranscriptRepository(fixture.engine).get(
            transcript_id_for(fixture.job.id)
        )
        is None
    )
    fixture.engine.dispose()


# -- idempotent resume (S14.14) -------------------------------------------------


class _CrashingJobs(SqliteTranscriptionJobRepository):
    """Simulates a process kill right before a given state would be persisted."""

    crash_before: TranscriptionJobState | None = None

    def save(self, job: TranscriptionJob) -> None:
        if job.state is self.crash_before:
            self.crash_before = None
            raise Crash
        super().save(job)


class _CrashingTranscripts(SqliteTranscriptRepository):
    crash = False

    def add(self, transcript: Transcript) -> None:
        if self.crash:
            self.crash = False
            raise Crash
        super().add(transcript)


class _CrashingSegments(SqliteSegmentRepository):
    crash_on_add: int | None = None
    adds = 0

    def add(self, segment: Segment) -> None:
        self.adds += 1
        if self.adds == self.crash_on_add:
            self.crash_on_add = None
            raise Crash
        super().add(segment)


Snapshot = tuple[str, str | None, list[tuple[int, int, str]], int]


def _snapshot(fixture: Harness) -> Snapshot:
    transcript = SqliteTranscriptRepository(fixture.engine).get(
        transcript_id_for(fixture.job.id)
    )
    assert transcript is not None
    stored = SqliteSegmentRepository(fixture.engine).list_by_transcript(transcript.id)
    assert len({segment.id for segment in stored}) == len(stored)
    return (
        fixture.persisted().state.value,
        transcript.language,
        [(s.start_ms, s.end_ms, s.text) for s in stored],
        len(fixture.checkpoints.list_for_job(fixture.job.id)),
    )


def _clean_snapshot(tmp_path: Path) -> Snapshot:
    fixture = harness(tmp_path / "clean", provider=Provider(content_text=True))
    finished = fixture.runner.run_job(fixture.job.id)
    assert finished is not None
    assert finished.state is TranscriptionJobState.COMPLETED
    snapshot = _snapshot(fixture)
    assert len(snapshot[2]) == 3
    fixture.engine.dispose()
    return snapshot


def _crash_then_resume(fixture: Harness) -> None:
    with pytest.raises(Crash):
        fixture.runner.run_job(fixture.job.id)
    interrupted = fixture.persisted()
    assert not interrupted.state.is_terminal
    # A restarted process: repositories are healthy again and recover() re-queues.
    fixture.runner.jobs = SqliteTranscriptionJobRepository(fixture.engine)
    fixture.runner.transcripts = SqliteTranscriptRepository(fixture.engine)
    fixture.runner.segments = SqliteSegmentRepository(fixture.engine)
    assert fixture.runner.recover() == (fixture.job.id,)
    finished = fixture.runner.run_job(fixture.job.id)
    assert finished is not None
    assert finished.state is TranscriptionJobState.COMPLETED


def test_resume_after_crash_while_preprocessing_matches_a_clean_run(
    tmp_path: Path,
) -> None:
    expected = _clean_snapshot(tmp_path)
    fixture = harness(
        tmp_path / "resumed", provider=Provider(content_text=True), derivative=False
    )
    fixture.preparer.crash_first = True

    _crash_then_resume(fixture)

    assert fixture.persisted().state is TranscriptionJobState.COMPLETED
    assert len(fixture.preparer.calls) == 2
    assert _snapshot(fixture) == expected
    fixture.engine.dispose()


@pytest.mark.parametrize("crash_call", [1, 2, 3])
def test_resume_after_crash_mid_chunks_matches_a_clean_run(
    tmp_path: Path, crash_call: int
) -> None:
    expected = _clean_snapshot(tmp_path)
    provider = Provider(content_text=True, crash_on_call=crash_call)
    fixture = harness(tmp_path / "resumed", provider=provider)

    _crash_then_resume(fixture)

    assert _snapshot(fixture) == expected
    # Committed chunks are never transcribed again; only the in-flight one repeats.
    assert provider.calls == 3 + 1
    fixture.engine.dispose()


def test_resume_after_last_chunk_committed_but_before_advancing(
    tmp_path: Path,
) -> None:
    expected = _clean_snapshot(tmp_path)
    provider = Provider(content_text=True)
    fixture = harness(tmp_path / "resumed", provider=provider)
    crashing = _CrashingJobs(fixture.engine)
    crashing.crash_before = TranscriptionJobState.ALIGNING
    fixture.runner.jobs = crashing

    _crash_then_resume(fixture)

    assert provider.calls == 3
    assert _snapshot(fixture) == expected
    fixture.engine.dispose()


@pytest.mark.parametrize("crash_on_add", [1, 2, 3])
def test_resume_after_crash_while_persisting_segments_adds_only_the_missing(
    tmp_path: Path, crash_on_add: int
) -> None:
    expected = _clean_snapshot(tmp_path)
    provider = Provider(content_text=True)
    fixture = harness(tmp_path / "resumed", provider=provider)
    segments = _CrashingSegments(fixture.engine)
    segments.crash_on_add = crash_on_add
    fixture.runner.segments = segments

    _crash_then_resume(fixture)

    assert provider.calls == 3
    assert _snapshot(fixture) == expected
    fixture.engine.dispose()


def test_resume_after_crash_before_transcript_insert_matches_a_clean_run(
    tmp_path: Path,
) -> None:
    expected = _clean_snapshot(tmp_path)
    fixture = harness(tmp_path / "resumed", provider=Provider(content_text=True))
    transcripts = _CrashingTranscripts(fixture.engine)
    transcripts.crash = True
    fixture.runner.transcripts = transcripts

    _crash_then_resume(fixture)

    assert _snapshot(fixture) == expected
    fixture.engine.dispose()


def test_persisting_twice_does_not_duplicate_segments(tmp_path: Path) -> None:
    expected = _clean_snapshot(tmp_path)
    fixture = harness(tmp_path / "resumed", provider=Provider(content_text=True))
    crashing = _CrashingJobs(fixture.engine)
    crashing.crash_before = TranscriptionJobState.COMPLETED
    fixture.runner.jobs = crashing

    # Everything is persisted, then the process dies before COMPLETED is saved.
    _crash_then_resume(fixture)

    assert fixture.provider.calls == 3
    assert _snapshot(fixture) == expected
    fixture.engine.dispose()


def test_recover_twice_does_not_duplicate_queued_jobs(tmp_path: Path) -> None:
    fixture = harness(tmp_path)

    first = fixture.runner.recover()
    second = fixture.runner.recover()
    fixture.runner.enqueue(fixture.job.id)

    assert first == second == (fixture.job.id,)
    assert fixture.runner._queue.qsize() == 1  # pyright: ignore[reportPrivateUsage]

    fixture.runner.start()
    try:
        assert fixture.runner.wait_idle(10.0)
        # Once drained, the job can be queued again (recover after a restart).
        assert fixture.runner.recover() == ()
    finally:
        fixture.runner.stop()
    assert fixture.persisted().state is TranscriptionJobState.COMPLETED
    assert fixture.provider.calls == 3
    fixture.engine.dispose()


class _SpacedProvider(Provider):
    """Whisper-style output: a leading word-boundary space and a blank span."""

    def _text(self, frames: bytes) -> str:
        return "   " if self.calls == 2 else f" chunk-{self.calls} "


def test_persisted_segments_drop_boundary_spaces_and_blank_spans(
    tmp_path: Path,
) -> None:
    fixture = harness(tmp_path, provider=_SpacedProvider())

    fixture.runner.run_job(fixture.job.id)

    segments = SqliteSegmentRepository(fixture.engine).list_by_transcript(
        transcript_id_for(fixture.job.id)
    )
    assert [s.text for s in segments] == ["chunk-1", "chunk-3"]
    fixture.engine.dispose()


class _WordProvider(Provider):
    """Emits padded and blank words the way raw Whisper output does."""

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        result = super().transcribe(
            audio=audio, options=options, cancellation=cancellation
        )
        (segment,) = result.segments
        half = segment.end_ms // 2
        words = (
            TranscriptionWord(0, half, " hola", 0.5),
            TranscriptionWord(half, half + 1, "  "),  # blank after strip: dropped
            TranscriptionWord(half + 1, segment.end_ms, " mundo "),
        )
        return TranscriptionResult(
            (TranscriptionSegment(0, segment.end_ms, segment.text, words=words),),
            result.language,
        )


WordSnapshot = list[tuple[int, int, list[tuple[int, int, str]]]]


def _word_snapshot(fixture: Harness) -> WordSnapshot:
    stored = SqliteSegmentRepository(fixture.engine).list_by_transcript(
        transcript_id_for(fixture.job.id)
    )
    all_ids = [w.id for s in stored for w in s.words]
    assert len(set(all_ids)) == len(all_ids)  # no duplicated word rows
    return [
        (s.start_ms, s.end_ms, [(w.start_ms, w.end_ms, w.text) for w in s.words])
        for s in stored
    ]


def test_job_persists_trimmed_words_inside_their_segments(tmp_path: Path) -> None:
    fixture = harness(tmp_path, provider=_WordProvider(content_text=True))

    fixture.runner.run_job(fixture.job.id)

    snapshot = _word_snapshot(fixture)
    assert [(start, end) for start, end, _ in snapshot] == [
        (0, 100),
        (100, 200),
        (200, 250),
    ]
    # The chunk-local words of chunk 0 cover 0-120 and are clamped to its 0-100
    # segment; blank words are gone and boundary spaces are stripped.
    assert snapshot[0][2] == [(0, 60, "hola"), (61, 100, "mundo")]
    for start, end, words in snapshot:
        assert words
        assert all(start <= w0 < w1 <= end for w0, w1, _ in words)
        assert all(a[1] <= b[0] for a, b in pairwise(words))
        assert all(text == text.strip() and text for _, _, text in words)
    fixture.engine.dispose()


@pytest.mark.parametrize("crash_on_add", [1, 2, 3])
def test_resume_after_crash_while_persisting_words_matches_a_clean_run(
    tmp_path: Path, crash_on_add: int
) -> None:
    clean = harness(tmp_path / "clean", provider=_WordProvider(content_text=True))
    clean.runner.run_job(clean.job.id)
    expected = _word_snapshot(clean)
    clean.engine.dispose()
    fixture = harness(tmp_path / "resumed", provider=_WordProvider(content_text=True))
    segments = _CrashingSegments(fixture.engine)
    segments.crash_on_add = crash_on_add
    fixture.runner.segments = segments

    _crash_then_resume(fixture)

    assert _word_snapshot(fixture) == expected
    fixture.engine.dispose()


def test_persisting_twice_does_not_duplicate_words(tmp_path: Path) -> None:
    fixture = harness(tmp_path, provider=_WordProvider(content_text=True))
    fixture.runner.run_job(fixture.job.id)
    expected = _word_snapshot(fixture)
    job = fixture.persisted()
    result = fixture.runner._result_from_checkpoints(job.id)  # pyright: ignore[reportPrivateUsage]

    selection = fixture.runner.selections.get(job.id)
    assert selection is not None
    fixture.runner._persist_transcript(job, selection, result)  # pyright: ignore[reportPrivateUsage]

    assert _word_snapshot(fixture) == expected
    fixture.engine.dispose()


def test_words_are_optional_the_job_completes_without_them(tmp_path: Path) -> None:
    fixture = harness(tmp_path)  # the base provider emits no words at all

    finished = fixture.runner.run_job(fixture.job.id)

    assert finished is not None
    assert finished.state is TranscriptionJobState.COMPLETED
    assert [words for _, _, words in _word_snapshot(fixture)] == [[], [], []]
    fixture.engine.dispose()
