"""A killed process resumes to the same transcript, with no rework or leftovers.

Each case "kills" the runner (``Crash`` is a ``BaseException``: nothing records
FAILED, exactly like a SIGKILL) at one critical point, then a brand-new runner on
the same SQLite database runs ``recover()``. The outcome must equal an uncrashed
run: same segments and identities, no duplicates, no chunk transcribed twice
unless its checkpoint never committed, and no derived file left behind.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportMissingImports=false

from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import uuid5

import pytest
import test_job_runner_diarization as diar

from voz.application.job_runner import JobRunner, transcript_id_for
from voz.application.ports.media_normalization import (
    MediaNormalizationCancellationToken,
)
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionOptions,
    TranscriptionResult,
)
from voz.application.ports.transcription_checkpoint import TranscriptionCheckpoint
from voz.domain.entities.segment import Segment
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
)
from voz.domain.entities.transcription_job import (
    TranscriptionJobState as S,
)
from voz.infrastructure.persistence.repositories import (
    SqliteSegmentRepository,
    SqliteSpeakerRepository,
    SqliteTranscriptRepository,
)
from voz.infrastructure.persistence.transcription_checkpoints import (
    SqliteTranscriptionCheckpointStore,
)

CHUNKS = 3  # 250 ms of audio in 100 ms chunks with 20 ms of overlap
SLICE_MS = 40  # several segments per chunk, so a partial write is observable
Snapshot = list[tuple[int, int, str, str | None]]


class FlakyAsr(diar.FakeAsr):
    """Dies before decoding its Nth call (1-based) and on no other call."""

    def __init__(
        self, timeline: diar.Timeline, *, slice_ms: int | None, crash_on_call: int = 0
    ) -> None:
        super().__init__(timeline, slice_ms=slice_ms)
        self.crash_on_call = crash_on_call
        self.calls = 0

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        self.calls += 1
        if self.calls == self.crash_on_call:
            raise diar.Crash
        return super().transcribe(
            audio=audio, options=options, cancellation=cancellation
        )


class CrashingCheckpoints(SqliteTranscriptionCheckpointStore):
    """The process dies after the chunk was decoded but before it was committed."""

    crash_on_chunk: int | None = None

    def commit(
        self, checkpoint: TranscriptionCheckpoint, job: TranscriptionJob
    ) -> None:
        if checkpoint.chunk_index == self.crash_on_chunk:
            raise diar.Crash
        super().commit(checkpoint, job)


class CrashingSegments(SqliteSegmentRepository):
    """The process dies after ``survivors`` segments were stored."""

    survivors = 10**9

    def add(self, segment: Segment) -> None:
        if self.survivors == 0:
            raise diar.Crash
        self.survivors -= 1
        super().add(segment)


class CopyPreparer:
    """Stands in for the normalizer: publishes the derivative, counts its runs."""

    def __init__(self, source: Path, destination: Path) -> None:
        self.source = source
        self.destination = destination
        self.calls = 0

    def prepare(
        self,
        *,
        project_id: object,
        media_asset_id: object,
        cancellation: MediaNormalizationCancellationToken | None = None,
        on_progress: object = None,
    ) -> None:
        self.calls += 1
        shutil.copyfile(self.source, self.destination)


@dataclass(slots=True)
class Case:
    """One crash point, how to arm it and what resuming must cost."""

    arm: Callable[[Scenario], None]
    left_in: S  # what the database says when the process dies
    kept_chunks: int  # checkpoints that survived the crash
    asr_calls: int  # chunks decoded across both runs (shared fake engine)
    diarize_calls: int = 1
    prepare_calls: int = 1


@dataclass(slots=True)
class Scenario:
    fx: diar.World
    jobs: diar.CrashingJobs
    checkpoints: CrashingCheckpoints
    asr: FlakyAsr
    preparer: CopyPreparer
    diarizer: diar.FakeDiarizer
    segments: CrashingSegments

    def runner(self, *, crashing: bool) -> JobRunner:
        runner = self.fx.runner(self.diarizer, jobs=self.jobs if crashing else None)
        runner.provider_for = lambda selection: self.asr
        runner.audio_preparer = self.preparer
        if crashing:
            runner.checkpoints = self.checkpoints
            runner.segments = self.segments
        return runner


def before_state(state: S) -> Callable[[Scenario], None]:
    def arm(scenario: Scenario) -> None:
        scenario.jobs.crash_before = state

    return arm


def asr_dies_on_call(call: int) -> Callable[[Scenario], None]:
    def arm(scenario: Scenario) -> None:
        scenario.asr.crash_on_call = call

    return arm


def commit_dies_on_chunk(chunk: int) -> Callable[[Scenario], None]:
    def arm(scenario: Scenario) -> None:
        scenario.checkpoints.crash_on_chunk = chunk

    return arm


def diarizer_dies(scenario: Scenario) -> None:
    def die() -> None:
        raise diar.Crash

    scenario.diarizer.before = die


def segment_write_dies(scenario: Scenario) -> None:
    scenario.segments.survivors = 2  # the third segment never reaches the database


CASES: dict[str, Case] = {
    # normalized, TRANSCRIBING never saved: the derivative is reused, not rebuilt
    "after-normalize": Case(before_state(S.TRANSCRIBING), S.PREPROCESSING, 0, CHUNKS),
    "mid-chunks-2nd-decode": Case(asr_dies_on_call(2), S.TRANSCRIBING, 1, CHUNKS),
    "mid-chunks-3rd-decode": Case(asr_dies_on_call(3), S.TRANSCRIBING, 2, CHUNKS),
    # chunk 1 was decoded but its checkpoint never committed: only that one repeats
    "mid-chunks-lost-commit": Case(
        commit_dies_on_chunk(1), S.TRANSCRIBING, 1, CHUNKS + 1
    ),
    "last-chunk-lost-commit": Case(
        commit_dies_on_chunk(CHUNKS - 1), S.TRANSCRIBING, 2, CHUNKS + 1
    ),
    "all-chunks-before-aligning": Case(
        before_state(S.ALIGNING), S.TRANSCRIBING, 3, CHUNKS
    ),
    "mid-segment-write": Case(segment_write_dies, S.ALIGNING, 3, CHUNKS),
    "after-asr-before-diarize": Case(before_state(S.DIARIZING), S.ALIGNING, 3, CHUNKS),
    "inside-diarization": Case(diarizer_dies, S.DIARIZING, 3, CHUNKS, diarize_calls=2),
    # DIARIZING has no checkpoint: diarization repeats, but assigning its turns again
    # must neither duplicate speakers nor change the labels (asserted below)
    "before-merging": Case(
        before_state(S.MERGING), S.DIARIZING, 3, CHUNKS, diarize_calls=2
    ),
    "before-persisting": Case(before_state(S.PERSISTING), S.MERGING, 3, CHUNKS),
    "during-persisting": Case(before_state(S.COMPLETED), S.PERSISTING, 3, CHUNKS),
}


def tree(root: Path) -> list[str]:
    """Files below ``root`` with identities masked, so two worlds compare."""
    uuid = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
    return sorted(
        uuid.sub("<id>", str(p.relative_to(root)))
        for p in root.rglob("*")
        if p.is_file()
    )


def snapshot(fx: diar.World) -> Snapshot:
    names = fx.segment_speakers()
    stored = SqliteSegmentRepository(fx.engine).list_by_transcript(
        transcript_id_for(fx.job.id)
    )
    return [
        (s.start_ms, s.end_ms, s.text, n) for s, n in zip(stored, names, strict=True)
    ]


def scenario(tmp_path: Path) -> Scenario:
    fx = diar.world(tmp_path, slice_ms=SLICE_MS)
    derivative = next((fx.root / "projects").rglob("*.inference.wav"))
    pristine = tmp_path / "pristine.wav"
    shutil.copyfile(derivative, pristine)
    derivative.unlink()  # the runner must produce it, as on a fresh import
    timeline = fx.timeline
    asr = FlakyAsr(timeline, slice_ms=SLICE_MS)
    return Scenario(
        fx=fx,
        jobs=diar.CrashingJobs(fx.engine),
        checkpoints=CrashingCheckpoints(fx.engine),
        asr=asr,
        preparer=CopyPreparer(pristine, derivative),
        diarizer=diar.FakeDiarizer(timeline),
        segments=CrashingSegments(fx.engine),
    )


@pytest.fixture(scope="module")
def reference(tmp_path_factory: pytest.TempPathFactory) -> tuple[Snapshot, list[str]]:
    """The uncrashed run every crashed run must reproduce."""
    tmp_path = tmp_path_factory.mktemp("reference")
    s = scenario(tmp_path)
    finished = s.runner(crashing=False).run_job(s.fx.job.id)
    assert finished is not None and finished.state is S.COMPLETED
    result = (snapshot(s.fx), tree(s.fx.root))
    s.fx.engine.dispose()
    return result


def test_reference_run_is_the_expected_shape(
    reference: tuple[Snapshot, list[str]],
) -> None:
    segments, files = reference
    assert len(segments) > CHUNKS  # several segments per chunk
    assert {speaker for *_, speaker in segments} == {"Speaker 1", "Speaker 2"}
    assert len(files) == 1 and files[0].endswith(".inference.wav")


@pytest.mark.parametrize("name", list(CASES))
def test_crash_then_recover_equals_an_uncrashed_run(
    tmp_path: Path, name: str, reference: tuple[Snapshot, list[str]]
) -> None:
    case = CASES[name]
    s = scenario(tmp_path)
    case.arm(s)

    with pytest.raises(diar.Crash):
        s.runner(crashing=True).run_job(s.fx.job.id)
    crashed = s.fx.persisted()
    assert crashed.state is case.left_in  # a kill never records FAILED
    assert (
        len(SqliteTranscriptionCheckpointStore(s.fx.engine).list_for_job(s.fx.job.id))
        == case.kept_chunks
    )

    # A new process: fresh runner, same database, healthy engines.
    s.asr.crash_on_call = 0
    s.diarizer.before = None
    resumed = s.runner(crashing=False)
    recovered = resumed.recover()
    assert recovered == (s.fx.job.id,)
    finished = resumed.run_job(recovered[0])

    assert finished is not None and finished.state is S.COMPLETED
    assert s.fx.persisted().state is S.COMPLETED
    # Same transcript as without the crash.
    expected_segments, expected_files = reference
    assert snapshot(s.fx) == expected_segments
    transcript_id = transcript_id_for(s.fx.job.id)
    stored = SqliteSegmentRepository(s.fx.engine).list_by_transcript(transcript_id)
    ids = [segment.id for segment in stored]
    assert len(set(ids)) == len(ids)  # no duplicates
    assert set(ids) <= {uuid5(transcript_id, f"segment:{i}") for i in range(100)}
    assert SqliteTranscriptRepository(s.fx.engine).get(transcript_id) is not None
    assert (
        len(SqliteSpeakerRepository(s.fx.engine).list_by_project(s.fx.job.project_id))
        == 2
    )
    # One checkpoint per chunk, none re-created under another identity.
    assert [
        c.chunk_index
        for c in SqliteTranscriptionCheckpointStore(s.fx.engine).list_for_job(
            s.fx.job.id
        )
    ] == list(range(CHUNKS))
    # Work is not repeated beyond what the crash destroyed.
    assert s.fx.timeline.events.count("asr.transcribe") == case.asr_calls
    assert s.fx.timeline.events.count("diarize") == case.diarize_calls
    assert s.preparer.calls == case.prepare_calls
    # No temporary or orphaned derivative: same files as the uncrashed run.
    assert tree(s.fx.root) == expected_files
    s.fx.engine.dispose()


def test_recovering_twice_does_not_redo_a_finished_job(
    tmp_path: Path,
) -> None:
    s = scenario(tmp_path)
    before_state(S.COMPLETED)(s)
    with pytest.raises(diar.Crash):
        s.runner(crashing=True).run_job(s.fx.job.id)
    first = s.runner(crashing=False)
    for job_id in first.recover():
        first.run_job(job_id)
    calls = (s.asr.calls, s.preparer.calls, s.fx.timeline.events.count("diarize"))
    before = snapshot(s.fx)

    second = s.runner(crashing=False)

    assert second.recover() == ()  # COMPLETED is terminal: nothing to resume
    assert second.run_job(s.fx.job.id) is not None
    assert (
        s.asr.calls,
        s.preparer.calls,
        s.fx.timeline.events.count("diarize"),
    ) == calls
    assert snapshot(s.fx) == before
    s.fx.engine.dispose()
