"""Cloud ASR speaker labels become Speaker entities (INTEGRITY-001, real SQLite)."""

from __future__ import annotations

import shutil
import wave
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy import Engine

from voz.application.assign_speakers import AssignProviderSpeakers, AssignSpeakers
from voz.application.job_runner import JobRunner, transcript_id_for
from voz.application.ports.diarization import (
    DiarizationOptions,
    DiarizationResult,
    DiarizedTurn,
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
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
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
    provider_id="fake-cloud",
    model_id="fixture",
    display_name="Fixture",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
)


class Crash(BaseException):
    """Simulates a process kill: not an ``Exception``, so nothing records FAILED."""


class LabelingAsr:
    """One segment per 100 ms chunk, labelled like a diarizing cloud provider."""

    provider_id = "fake-cloud"

    def __init__(self, labels: list[str | None]) -> None:
        self.labels = labels
        self.calls = 0

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        del options, cancellation
        with wave.open(audio, "rb") as source:
            duration_ms = source.getnframes() * 1_000 // source.getframerate()
        label = self.labels[self.calls]
        self.calls += 1
        return TranscriptionResult(
            (TranscriptionSegment(0, duration_ms, f"t{self.calls}", speaker=label),),
            "es",
        )


class LocalDiarizer:
    provider_id = "fake-diarization"

    def diarize(
        self,
        *,
        audio: BinaryIO,
        options: DiarizationOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> DiarizationResult:
        del audio, options, cancellation
        return DiarizationResult((DiarizedTurn(0, 250, "L"),))


class NoPreparer:
    def prepare(
        self,
        *,
        project_id: object,
        media_asset_id: object,
        cancellation: MediaNormalizationCancellationToken | None = None,
    ) -> None:
        raise AssertionError("derivative already exists")


class CrashingJobs(SqliteTranscriptionJobRepository):
    crash_before: TranscriptionJobState | None = None

    def save(self, job: TranscriptionJob) -> None:
        if job.state is self.crash_before:
            self.crash_before = None
            raise Crash
        super().save(job)


class BrokenSpeakers(SqliteSpeakerRepository):
    def add(self, speaker: Speaker) -> None:
        raise RuntimeError("disk full")


@dataclass(slots=True)
class World:
    engine: Engine
    job: TranscriptionJob
    root: Path

    def runner(
        self,
        asr: LabelingAsr,
        *,
        jobs: SqliteTranscriptionJobRepository | None = None,
        speakers: SqliteSpeakerRepository | None = None,
        local: bool = False,
    ) -> JobRunner:
        ticks = iter(range(1, 10_000))
        segments = SqliteSegmentRepository(self.engine)
        speaker_repo = speakers or SqliteSpeakerRepository(self.engine)
        return JobRunner(
            jobs=jobs or SqliteTranscriptionJobRepository(self.engine),
            selections=SqliteTranscriptionJobSelectionRepository(self.engine),
            media_assets=SqliteMediaAssetRepository(self.engine),
            transcripts=SqliteTranscriptRepository(self.engine),
            segments=segments,
            checkpoints=SqliteTranscriptionCheckpointStore(self.engine),
            provider_for=lambda selection: asr,
            audio_source_for=lambda project_id, media_asset_id: (
                FileSystemInferenceAudioSource(self.root, project_id, media_asset_id)
            ),
            audio_preparer=NoPreparer(),
            clock=lambda: BASE_TIME + timedelta(seconds=next(ticks)),
            diarization_provider_for=(lambda: LocalDiarizer()) if local else None,
            assign_speakers=AssignSpeakers(
                SqliteTranscriptRepository(self.engine),
                segments,
                speaker_repo,
                SqliteSpeakerTurnRepository(self.engine),
            ),
            assign_provider_speakers=AssignProviderSpeakers(speaker_repo, segments),
            chunk_duration_ms=100,
            overlap_ms=20,
        )

    def names(self) -> list[str | None]:
        by_id = {
            s.id: s.name
            for s in SqliteSpeakerRepository(self.engine).list_by_project(
                self.job.project_id
            )
        }
        return [
            None if s.speaker_id is None else by_id[s.speaker_id]
            for s in SqliteSegmentRepository(self.engine).list_by_transcript(
                transcript_id_for(self.job.id)
            )
        ]

    def speaker_count(self) -> int:
        return len(
            SqliteSpeakerRepository(self.engine).list_by_project(self.job.project_id)
        )

    def selection(self) -> JobSelection:
        selection = SqliteTranscriptionJobSelectionRepository(self.engine).get(
            self.job.id
        )
        assert selection is not None
        return selection


def world(tmp_path: Path, *, diarization: DiarizationOptions | None = None) -> World:
    engine = create_sqlite_engine((tmp_path / "voz.db").absolute())
    upgrade_to_head(engine)
    project = Project("Demo", created_at=BASE_TIME)
    SqliteProjectRepository(engine).add(project)
    asset = MediaAsset(project.id, "a" * 64, "tone.wav", 8_044, duration_ms=250)
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
        )
    )
    root = tmp_path / "data"
    target = root / "projects" / str(project.id) / "derivatives"
    target.mkdir(parents=True)
    shutil.copyfile(WAV_FIXTURE, target / f"{asset.id}.inference.wav")
    return World(engine, job, root)


def test_provider_labels_become_speakers_in_order_of_appearance(
    tmp_path: Path,
) -> None:
    fixture = world(tmp_path)

    finished = fixture.runner(LabelingAsr(["B", "A", "B"])).run_job(fixture.job.id)

    assert finished is not None
    assert finished.state is TranscriptionJobState.COMPLETED
    assert fixture.names() == ["Hablante 1", "Hablante 2", "Hablante 1"]
    transcript_id = transcript_id_for(fixture.job.id)
    speakers = SqliteSpeakerRepository(fixture.engine).list_by_transcript(transcript_id)
    assert [s.name for s in speakers] == ["Hablante 1", "Hablante 2"]
    assert {s.id for s in speakers} == {
        uuid5(transcript_id, "speaker:B"),
        uuid5(transcript_id, "speaker:A"),
    }
    assert len({s.color for s in speakers}) == 2
    assert not SqliteSpeakerTurnRepository(fixture.engine).list_by_transcript(
        transcript_id
    )
    fixture.engine.dispose()


def test_unlabelled_segments_keep_no_speaker_and_create_none(tmp_path: Path) -> None:
    fixture = world(tmp_path)

    fixture.runner(LabelingAsr([None, None, None])).run_job(fixture.job.id)

    assert fixture.names() == [None, None, None]
    assert fixture.speaker_count() == 0
    fixture.engine.dispose()


def test_local_diarization_wins_over_provider_labels(tmp_path: Path) -> None:
    fixture = world(tmp_path, diarization=DiarizationOptions())

    fixture.runner(LabelingAsr(["A", "B", "A"]), local=True).run_job(fixture.job.id)

    assert fixture.names() == ["Speaker 1"] * 3
    assert fixture.speaker_count() == 1
    fixture.engine.dispose()


def test_resume_after_crash_reuses_speakers_and_keeps_renames(tmp_path: Path) -> None:
    fixture = world(tmp_path)
    jobs = CrashingJobs(fixture.engine)
    jobs.crash_before = TranscriptionJobState.COMPLETED
    with pytest.raises(Crash):
        fixture.runner(LabelingAsr(["A", "B", "A"]), jobs=jobs).run_job(fixture.job.id)
    assert fixture.names() == ["Hablante 1", "Hablante 2", "Hablante 1"]
    speakers = SqliteSpeakerRepository(fixture.engine)
    first = speakers.list_by_project(fixture.job.project_id)[0]
    speakers.save(first.rename("Ana", updated_at=first.updated_at))

    finished = fixture.runner(LabelingAsr(["A", "B", "A"])).run_job(fixture.job.id)

    assert finished is not None
    assert finished.state is TranscriptionJobState.COMPLETED
    assert fixture.names() == ["Ana", "Hablante 2", "Ana"]
    assert fixture.speaker_count() == 2
    fixture.engine.dispose()


def test_speaker_failure_is_recorded_and_the_transcript_is_kept(
    tmp_path: Path,
) -> None:
    fixture = world(tmp_path)
    broken = BrokenSpeakers(fixture.engine)

    finished = fixture.runner(LabelingAsr(["A", "B", "A"]), speakers=broken).run_job(
        fixture.job.id
    )

    assert finished is not None
    assert finished.state is TranscriptionJobState.COMPLETED
    assert fixture.selection().diarization_error_code == "diarization_provider_failed"
    assert fixture.names() == [None, None, None]
    fixture.engine.dispose()


def test_assign_provider_speakers_is_idempotent(tmp_path: Path) -> None:
    fixture = world(tmp_path)
    runner = fixture.runner(LabelingAsr(["A", "B", "A"]))
    runner.run_job(fixture.job.id)
    transcript_id = transcript_id_for(fixture.job.id)
    segments = SqliteSegmentRepository(fixture.engine).list_by_transcript(transcript_id)
    labels: dict[UUID, str] = {
        segments[0].id: "A",
        segments[1].id: "B",
        segments[2].id: "A",
    }
    use_case = AssignProviderSpeakers(
        SqliteSpeakerRepository(fixture.engine), SqliteSegmentRepository(fixture.engine)
    )

    first = use_case.execute(transcript_id, fixture.job.project_id, labels)
    second = use_case.execute(transcript_id, fixture.job.project_id, labels)

    assert [s.id for s in first] == [s.id for s in second]
    assert fixture.speaker_count() == 2
    fixture.engine.dispose()
