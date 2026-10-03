"""JobRunner diarization stage over real SQLite with fake engines (S6.13/S6.15)."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import os
import shutil
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import pytest
from sqlalchemy import Engine

from voz.application.assign_speakers import AssignSpeakers
from voz.application.job_runner import JobRunner, transcript_id_for
from voz.application.ports.diarization import (
    DiarizationError,
    DiarizationFailureCode,
    DiarizationOptions,
    DiarizationProvider,
    DiarizationResult,
    DiarizedTurn,
    SpeakerCountHint,
)
from voz.application.ports.media_normalization import (
    MediaNormalizationCancellationToken,
)
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionOptions,
    TranscriptionResult,
    TranscriptionSegment,
)
from voz.application.ports.transcription_job_selection import JobSelection
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.project import Project
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.infrastructure.diarization.sherpa import SherpaOnnxDiarizationProvider
from voz.infrastructure.inference_audio import FileSystemInferenceAudioSource
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.migrate import upgrade_to_head
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteSegmentRepository,
    SqliteSpeakerRepository,
    SqliteSpeakerTurnRepository,
    SqliteTranscriptionJobRepository,
    SqliteTranscriptRepository,
)
from voz.infrastructure.persistence.transcription_checkpoints import (
    SqliteTranscriptionCheckpointStore,
)
from voz.infrastructure.persistence.transcription_job_selections import (
    SqliteTranscriptionJobSelectionRepository,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
WAV_FIXTURE = REPOSITORY_ROOT / "tests/fixtures/media/synthetic-tone.wav"
BASE_TIME = datetime(2026, 9, 30, 12, tzinfo=UTC)
DESCRIPTOR = ModelDescriptor(
    provider_id="fake-asr",
    model_id="fixture",
    display_name="Fixture",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    source="example/fake-asr",
    revision="f" * 40,
)
AUTO = DiarizationOptions()
TWO_SPEAKERS = DiarizationResult(
    (DiarizedTurn(0, 100, "0"), DiarizedTurn(100, 250, "1"))
)


class Crash(BaseException):
    """Simulates a process kill: not an ``Exception``, so nothing records FAILED."""


@dataclass(slots=True)
class Timeline:
    """Shared ordered log of what the fake engines did."""

    events: list[str] = field(default_factory=list[str])


class FakeAsr:
    """One segment per clip; ``close`` is the ASR release observed by the test."""

    provider_id = "fake-asr"

    def __init__(self, timeline: Timeline, *, slice_ms: int | None = None) -> None:
        self.timeline = timeline
        self.slice_ms = slice_ms
        self.prompts: list[str | None] = []

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        del cancellation
        self.prompts.append(options.prompt)
        with wave.open(audio, "rb") as source:
            duration_ms = source.getnframes() * 1_000 // source.getframerate()
        self.timeline.events.append("asr.transcribe")
        step = self.slice_ms or duration_ms
        starts = range(0, duration_ms, step)
        return TranscriptionResult(
            tuple(
                TranscriptionSegment(start, min(start + step, duration_ms), f"t{start}")
                for start in starts
            ),
            "es",
        )

    def close(self) -> None:
        self.timeline.events.append("asr.close")


class FakeDiarizer:
    provider_id = "fake-diarization"

    def __init__(
        self,
        timeline: Timeline,
        *,
        result: DiarizationResult = TWO_SPEAKERS,
        error: BaseException | None = None,
        before: Callable[[], object] | None = None,
        fractions: tuple[float, ...] = (),
        after_progress: Callable[[], object] | None = None,
    ) -> None:
        self.timeline = timeline
        self.result = result
        self.error = error
        self.before = before
        self.fractions = fractions
        self.after_progress = after_progress
        self.options: list[DiarizationOptions] = []

    def diarize(
        self,
        *,
        audio: BinaryIO,
        options: DiarizationOptions,
        cancellation: TranscriptionCancellationToken | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> DiarizationResult:
        self.timeline.events.append("diarize")
        self.options.append(options)
        with wave.open(audio, "rb") as source:  # the same normalized derivative
            assert source.getframerate() == 16_000
        if self.before is not None:
            self.before()
        for fraction in self.fractions:
            assert on_progress is not None
            on_progress(fraction)
        if self.after_progress is not None:
            self.after_progress()
        if cancellation is not None and cancellation.is_cancelled():
            raise DiarizationError(DiarizationFailureCode.CANCELLED, "cancelled")
        if self.error is not None:
            raise self.error
        return self.result


class NoPreparer:
    def prepare(
        self,
        *,
        project_id: object,
        media_asset_id: object,
        cancellation: MediaNormalizationCancellationToken | None = None,
        on_progress: object = None,
    ) -> None:
        raise AssertionError("derivative already exists")


class CrashingJobs(SqliteTranscriptionJobRepository):
    """Kill the process right before a given state would be persisted."""

    crash_before: TranscriptionJobState | None = None

    def save(self, job: TranscriptionJob) -> None:
        if job.state is self.crash_before:
            self.crash_before = None
            raise Crash
        super().save(job)


@dataclass(slots=True)
class World:
    engine: Engine
    job: TranscriptionJob
    root: Path
    timeline: Timeline
    asr: FakeAsr

    def runner(
        self,
        diarizer: DiarizationProvider | None,
        *,
        jobs: SqliteTranscriptionJobRepository | None = None,
        assign: bool = True,
    ) -> JobRunner:
        ticks = iter(range(1, 10_000))
        transcripts = SqliteTranscriptRepository(self.engine)
        segments = SqliteSegmentRepository(self.engine)
        return JobRunner(
            jobs=jobs or SqliteTranscriptionJobRepository(self.engine),
            selections=SqliteTranscriptionJobSelectionRepository(self.engine),
            media_assets=SqliteMediaAssetRepository(self.engine),
            transcripts=transcripts,
            segments=segments,
            checkpoints=SqliteTranscriptionCheckpointStore(self.engine),
            provider_for=lambda selection: self.asr,
            audio_source_for=lambda project_id, media_asset_id: (
                FileSystemInferenceAudioSource(self.root, project_id, media_asset_id)
            ),
            audio_preparer=NoPreparer(),
            clock=lambda: BASE_TIME + timedelta(seconds=next(ticks)),
            diarization_provider_for=None if diarizer is None else lambda: diarizer,
            assign_speakers=AssignSpeakers(
                transcripts,
                segments,
                SqliteSpeakerRepository(self.engine),
                SqliteSpeakerTurnRepository(self.engine),
            )
            if assign
            else None,
            release_asr=lambda selection: self.asr.close(),
            chunk_duration_ms=100,
            overlap_ms=20,
        )

    def persisted(self) -> TranscriptionJob:
        job = SqliteTranscriptionJobRepository(self.engine).get(self.job.id)
        assert job is not None
        return job

    def selection(self) -> JobSelection:
        selection = SqliteTranscriptionJobSelectionRepository(self.engine).get(
            self.job.id
        )
        assert selection is not None
        return selection

    def segment_speakers(self) -> list[str | None]:
        speakers = {
            s.id: s.name
            for s in SqliteSpeakerRepository(self.engine).list_by_project(
                self.job.project_id
            )
        }
        return [
            None if s.speaker_id is None else speakers[s.speaker_id]
            for s in SqliteSegmentRepository(self.engine).list_by_transcript(
                transcript_id_for(self.job.id)
            )
        ]


def world(
    tmp_path: Path,
    *,
    diarization: DiarizationOptions | None = AUTO,
    wav: Path = WAV_FIXTURE,
    duration_ms: int = 250,
    slice_ms: int | None = None,
    prompt: str | None = None,
) -> World:
    engine = create_sqlite_engine((tmp_path / "voz.db").absolute())
    upgrade_to_head(engine)  # the real migration, including 0005
    project = Project("Demo", created_at=BASE_TIME)
    SqliteProjectRepository(engine).add(project)
    asset = MediaAsset(project.id, "a" * 64, "tone.wav", 8_044, duration_ms=duration_ms)
    SqliteMediaAssetRepository(engine).add(asset)
    job = TranscriptionJob.create(
        job_id=uuid4(), project_id=project.id, media_asset_id=asset.id, now=BASE_TIME
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
            diarization=diarization,
            prompt=prompt,
        )
    )
    root = tmp_path / "data"
    target = root / "projects" / str(project.id) / "derivatives"
    target.mkdir(parents=True)
    shutil.copyfile(wav, target / f"{asset.id}.inference.wav")
    timeline = Timeline()
    return World(engine, job, root, timeline, FakeAsr(timeline, slice_ms=slice_ms))


def test_two_speakers_label_segments_and_store_turns(tmp_path: Path) -> None:
    fixture = world(tmp_path, diarization=DiarizationOptions(SpeakerCountHint(exact=2)))
    diarizer = FakeDiarizer(fixture.timeline)

    finished = fixture.runner(diarizer).run_job(fixture.job.id)

    assert finished is not None
    assert finished.state is TranscriptionJobState.COMPLETED
    # Segments are 0-100, 100-200, 200-250; turns are A 0-100 and B 100-250.
    assert fixture.segment_speakers() == ["Speaker 1", "Speaker 2", "Speaker 2"]
    turns = SqliteSpeakerTurnRepository(fixture.engine).list_by_transcript(
        transcript_id_for(fixture.job.id)
    )
    assert [(t.start_ms, t.end_ms, t.cluster_label) for t in turns] == [
        (0, 100, "0"),
        (100, 250, "1"),
    ]
    assert len({t.speaker_id for t in turns}) == 2
    assert diarizer.options == [DiarizationOptions(SpeakerCountHint(exact=2))]
    assert fixture.selection().diarization_error_code is None
    fixture.engine.dispose()


def test_asr_is_released_before_diarization_starts(tmp_path: Path) -> None:
    fixture = world(tmp_path)

    fixture.runner(FakeDiarizer(fixture.timeline)).run_job(fixture.job.id)

    events = fixture.timeline.events
    assert events == ["asr.transcribe"] * 3 + ["asr.close", "diarize"]
    fixture.engine.dispose()


def test_disabled_diarization_never_touches_engines(tmp_path: Path) -> None:
    fixture = world(tmp_path, diarization=None)
    diarizer = FakeDiarizer(fixture.timeline)

    finished = fixture.runner(diarizer).run_job(fixture.job.id)

    assert finished is not None
    assert finished.state is TranscriptionJobState.COMPLETED
    assert fixture.timeline.events == ["asr.transcribe"] * 3
    assert fixture.segment_speakers() == [None, None, None]
    assert (
        SqliteSpeakerTurnRepository(fixture.engine).list_by_transcript(
            transcript_id_for(fixture.job.id)
        )
        == ()
    )
    fixture.engine.dispose()


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (
            DiarizationError(DiarizationFailureCode.MODEL_UNAVAILABLE, "/private/x"),
            "diarization_model_unavailable",
        ),
        (RuntimeError("/private/boom"), "diarization_provider_failed"),
    ],
)
def test_diarization_failure_keeps_the_transcript(
    tmp_path: Path, error: Exception, code: str
) -> None:
    fixture = world(tmp_path)

    finished = fixture.runner(FakeDiarizer(fixture.timeline, error=error)).run_job(
        fixture.job.id
    )

    assert finished is not None
    assert finished.state is TranscriptionJobState.COMPLETED
    assert finished.error_code is None
    assert fixture.selection().diarization_error_code == code
    assert fixture.segment_speakers() == [None, None, None]
    assert len(fixture.timeline.events) == 5  # 3 chunks, release, one diarize call
    fixture.engine.dispose()


def test_unwired_diarization_records_runtime_unavailable(tmp_path: Path) -> None:
    fixture = world(tmp_path)

    finished = fixture.runner(None).run_job(fixture.job.id)

    assert finished is not None
    assert finished.state is TranscriptionJobState.COMPLETED
    assert (
        fixture.selection().diarization_error_code == "diarization_runtime_unavailable"
    )
    fixture.engine.dispose()


def test_assignment_failure_keeps_the_transcript(tmp_path: Path) -> None:
    fixture = world(tmp_path)

    finished = fixture.runner(FakeDiarizer(fixture.timeline), assign=False).run_job(
        fixture.job.id
    )

    assert finished is not None
    assert finished.state is TranscriptionJobState.COMPLETED
    assert (
        fixture.selection().diarization_error_code == "diarization_runtime_unavailable"
    )
    assert len(fixture.segment_speakers()) == 3
    fixture.engine.dispose()


def test_cancel_during_diarization_cancels_but_keeps_the_text(tmp_path: Path) -> None:
    fixture = world(tmp_path)
    runner = fixture.runner(None)
    diarizer = FakeDiarizer(
        fixture.timeline, before=lambda: runner.cancel(fixture.job.id)
    )
    runner.diarization_provider_for = lambda: diarizer

    finished = runner.run_job(fixture.job.id)

    assert finished is not None
    assert finished.state is TranscriptionJobState.CANCELLED
    assert fixture.persisted().state is TranscriptionJobState.CANCELLED
    assert fixture.selection().diarization_error_code is None
    # The text was already persisted when diarization began: cancelling the
    # speakers does not throw the transcription away.
    assert (
        SqliteTranscriptRepository(fixture.engine).get(
            transcript_id_for(fixture.job.id)
        )
        is not None
    )
    assert fixture.segment_speakers() == [None, None, None]
    fixture.engine.dispose()


def test_shutdown_during_diarization_leaves_job_resumable(tmp_path: Path) -> None:
    fixture = world(tmp_path)
    runner = fixture.runner(None)
    diarizer = FakeDiarizer(fixture.timeline, before=runner.stop)
    runner.diarization_provider_for = lambda: diarizer

    interrupted = runner.run_job(fixture.job.id)

    assert interrupted is not None
    assert interrupted.state is TranscriptionJobState.DIARIZING
    assert fixture.selection().diarization_error_code is None

    resumed = fixture.runner(FakeDiarizer(fixture.timeline)).run_job(fixture.job.id)

    assert resumed is not None
    assert resumed.state is TranscriptionJobState.COMPLETED
    assert fixture.segment_speakers() == ["Speaker 1", "Speaker 2", "Speaker 2"]
    fixture.engine.dispose()


def test_resume_in_persisting_keeps_speakers_without_rediarizing(
    tmp_path: Path,
) -> None:
    fixture = world(tmp_path)
    jobs = CrashingJobs(fixture.engine)
    jobs.crash_before = TranscriptionJobState.COMPLETED
    with pytest.raises(Crash):
        fixture.runner(FakeDiarizer(fixture.timeline), jobs=jobs).run_job(
            fixture.job.id
        )
    assert fixture.persisted().state is TranscriptionJobState.PERSISTING
    assert fixture.timeline.events.count("diarize") == 1

    resumed = fixture.runner(FakeDiarizer(fixture.timeline)).run_job(fixture.job.id)

    assert resumed is not None
    assert resumed.state is TranscriptionJobState.COMPLETED
    # Speakers are assigned inside DIARIZING now, so nothing is redone.
    assert fixture.timeline.events.count("diarize") == 1
    assert fixture.timeline.events.count("asr.transcribe") == 3  # ASR not repeated
    assert fixture.segment_speakers() == ["Speaker 1", "Speaker 2", "Speaker 2"]
    assert (
        len(
            SqliteSpeakerRepository(fixture.engine).list_by_project(
                fixture.job.project_id
            )
        )
        == 2
    )
    fixture.engine.dispose()


def test_text_is_persisted_and_visible_before_speakers_are_assigned(
    tmp_path: Path,
) -> None:
    fixture = world(tmp_path)
    seen: list[tuple[TranscriptionJobState, int, list[str | None]]] = []

    def look() -> None:
        seen.append(
            (
                fixture.persisted().state,
                len(
                    SqliteSegmentRepository(fixture.engine).list_by_transcript(
                        transcript_id_for(fixture.job.id)
                    )
                ),
                fixture.segment_speakers(),
            )
        )

    runner = fixture.runner(FakeDiarizer(fixture.timeline, before=look))

    finished = runner.run_job(fixture.job.id)

    # While the speakers were being computed the whole text was already stored,
    # with nobody assigned yet; afterwards the same rows got their speakers.
    assert seen == [(TranscriptionJobState.DIARIZING, 3, [None, None, None])]
    assert finished is not None
    assert finished.state is TranscriptionJobState.COMPLETED
    assert fixture.segment_speakers() == ["Speaker 1", "Speaker 2", "Speaker 2"]
    segments = SqliteSegmentRepository(fixture.engine).list_by_transcript(
        transcript_id_for(fixture.job.id)
    )
    assert len(segments) == 3  # assigned in place, not duplicated
    fixture.engine.dispose()


def test_diarization_failure_still_leaves_the_text_stored(tmp_path: Path) -> None:
    fixture = world(tmp_path)
    error = DiarizationError(DiarizationFailureCode.PROVIDER_FAILED, "boom")
    runner = fixture.runner(FakeDiarizer(fixture.timeline, error=error))

    finished = runner.run_job(fixture.job.id)

    assert finished is not None
    assert finished.state is TranscriptionJobState.COMPLETED
    assert fixture.selection().diarization_error_code == "diarization_provider_failed"
    assert fixture.segment_speakers() == [None, None, None]
    fixture.engine.dispose()


def test_stage_progress_timing_and_weighted_global_progress(tmp_path: Path) -> None:
    fixture = world(tmp_path)
    during: list[TranscriptionJob] = []
    diarizer = FakeDiarizer(
        fixture.timeline,
        fractions=(0.5,),
        after_progress=lambda: during.append(fixture.persisted()),
    )
    runner = fixture.runner(diarizer)

    finished = runner.run_job(fixture.job.id)

    (mid,) = during
    assert mid.state is TranscriptionJobState.DIARIZING
    assert mid.stage_progress == 0.5
    assert mid.progress == pytest.approx(0.8 + 0.18 * 0.5)  # speakers: 0.8..0.98
    assert mid.started_at is not None
    assert mid.stage_started_at is not None
    assert mid.started_at <= mid.stage_started_at <= mid.updated_at
    assert finished is not None and finished.progress == 1.0
    assert finished.stage_progress is None
    # Transcription ends where the speakers start, never at 100 %.
    checkpoints = SqliteTranscriptionCheckpointStore(fixture.engine).list_for_job(
        fixture.job.id
    )
    assert checkpoints[-1].job_progress == pytest.approx(0.8)
    assert [c.job_progress for c in checkpoints] == sorted(
        c.job_progress for c in checkpoints
    )
    fixture.engine.dispose()


def test_global_progress_never_reads_complete_while_diarizing(tmp_path: Path) -> None:
    fixture = world(tmp_path)
    during: list[TranscriptionJob] = []
    runner = fixture.runner(
        FakeDiarizer(
            fixture.timeline, after_progress=lambda: during.append(fixture.persisted())
        )
    )

    runner.run_job(fixture.job.id)

    assert during[0].state is TranscriptionJobState.DIARIZING
    assert during[0].progress == pytest.approx(0.8)


def test_cancel_after_progress_is_not_overwritten_by_a_late_save(
    tmp_path: Path,
) -> None:
    fixture = world(tmp_path)
    runner = fixture.runner(None)
    diarizer = FakeDiarizer(
        fixture.timeline,
        fractions=(0.3,),
        before=lambda: runner.cancel(fixture.job.id),
    )
    runner.diarization_provider_for = lambda: diarizer

    finished = runner.run_job(fixture.job.id)

    assert finished is not None
    assert finished.state is TranscriptionJobState.CANCELLED
    assert fixture.persisted().state is TranscriptionJobState.CANCELLED
    fixture.engine.dispose()


def test_style_prompt_reaches_the_asr_engine(tmp_path: Path) -> None:
    fixture = world(tmp_path, diarization=None, prompt="Usa tildes y signos.")
    runner = fixture.runner(None)

    runner.run_job(fixture.job.id)

    assert fixture.asr.prompts and set(fixture.asr.prompts) == {"Usa tildes y signos."}
    fixture.engine.dispose()


_MODELS_DIR = os.environ.get("VOZ_DIARIZATION_E2E_MODELS")
_AUDIO = os.environ.get("VOZ_DIARIZATION_E2E_AUDIO")


@pytest.mark.skipif(
    not (_MODELS_DIR and _AUDIO),
    reason="opt-in: set VOZ_DIARIZATION_E2E_MODELS and VOZ_DIARIZATION_E2E_AUDIO",
)
def test_real_sherpa_labels_a_two_voice_dialogue(tmp_path: Path) -> None:
    pytest.importorskip("sherpa_onnx")
    assert _MODELS_DIR and _AUDIO
    with wave.open(_AUDIO, "rb") as source:
        duration_ms = source.getnframes() * 1_000 // source.getframerate()
    fixture = world(tmp_path, wav=Path(_AUDIO), duration_ms=duration_ms, slice_ms=1_000)
    provider = SherpaOnnxDiarizationProvider(
        segmentation_model=Path(_MODELS_DIR) / "pyannote-segmentation-3-0.onnx",
        embedding_model=Path(_MODELS_DIR) / "wespeaker_en_voxceleb_resnet34_LM.onnx",
    )
    try:
        runner = fixture.runner(provider)
        runner.chunk_duration_ms = 30 * 60 * 1_000  # a single ASR chunk
        runner.overlap_ms = 0
        finished = runner.run_job(fixture.job.id)
    finally:
        provider.close()

    assert finished is not None
    assert finished.state is TranscriptionJobState.COMPLETED
    assert fixture.selection().diarization_error_code is None
    turns = SqliteSpeakerTurnRepository(fixture.engine).list_by_transcript(
        transcript_id_for(fixture.job.id)
    )
    assert len({t.cluster_label for t in turns}) >= 2
    labels = {name for name in fixture.segment_speakers() if name is not None}
    assert len(labels) >= 2
    assert fixture.timeline.events.index("asr.close") > 0
    fixture.engine.dispose()
