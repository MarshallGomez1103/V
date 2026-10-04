"""Speakers-only rerun of a finished transcript (CP-A3): no re-transcription."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import shutil
import wave
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO, cast
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from voz.application.assign_speakers import AssignSpeakers
from voz.application.create_transcription_job import CreateTranscriptionJob
from voz.application.job_runner import JobRunner, transcript_id_for
from voz.application.ports.diarization import (
    DiarizationOptions,
    DiarizationResult,
    DiarizedTurn,
    SpeakerCountHint,
)
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionOptions,
    TranscriptionResult,
)
from voz.application.ports.transcription_job_selection import JobSelection
from voz.application.rediarize import (
    RediarizeError,
    RediarizeFailureCode,
    RediarizeTranscript,
)
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.project import Project
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.speaker_turn import SpeakerTurn
from voz.domain.entities.transcript import Transcript
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
from voz.interfaces.api.jobs import create_jobs_router

WAV_FIXTURE = Path(__file__).parents[3] / "tests/fixtures/media/synthetic-tone.wav"
T0 = datetime(2026, 10, 1, 12, tzinfo=UTC)
DESCRIPTOR = ModelDescriptor(
    provider_id="fake-asr",
    model_id="fixture",
    display_name="Fixture",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    source="example/fake-asr",
    revision="f" * 40,
)


class NoAsr:
    provider_id = "fake-asr"

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        raise AssertionError("a speakers-only rerun must not transcribe")


class Diarizer:
    provider_id = "fake-diarization"

    def __init__(self, result: DiarizationResult) -> None:
        self.result = result
        self.options: list[DiarizationOptions] = []

    def diarize(
        self,
        *,
        audio: BinaryIO,
        options: DiarizationOptions,
        cancellation: TranscriptionCancellationToken | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> DiarizationResult:
        with wave.open(audio, "rb"):
            pass
        self.options.append(options)
        if on_progress is not None:
            on_progress(0.5)
        return self.result


class Availability:
    def __init__(self, *, runtime: bool = True, models: bool = True) -> None:
        self.runtime = runtime
        self.models = models

    def runtime_available(self) -> bool:
        return self.runtime

    def models_installed(self) -> bool:
        return self.models

    def is_available(self) -> bool:
        return self.runtime and self.models


class NoPreparer:
    def prepare(self, **_: object) -> None:
        raise AssertionError("derivative already exists")


@dataclass(slots=True)
class World:
    engine: Engine
    job: TranscriptionJob
    root: Path
    teacher: Speaker
    student: Speaker

    @property
    def transcript_id(self) -> UUID:
        return transcript_id_for(self.job.id)

    def use_case(self, availability: Availability | None = None) -> RediarizeTranscript:
        return RediarizeTranscript(
            SqliteTranscriptRepository(self.engine),
            SqliteTranscriptionJobRepository(self.engine),
            SqliteTranscriptionJobSelectionRepository(self.engine),
            availability or Availability(),
            clock=lambda: T0 + timedelta(hours=1),
        )

    def runner(self, diarizer: Diarizer) -> JobRunner:
        ticks = iter(range(1, 10_000))
        transcripts = SqliteTranscriptRepository(self.engine)
        segments = SqliteSegmentRepository(self.engine)
        return JobRunner(
            jobs=SqliteTranscriptionJobRepository(self.engine),
            selections=SqliteTranscriptionJobSelectionRepository(self.engine),
            media_assets=SqliteMediaAssetRepository(self.engine),
            transcripts=transcripts,
            segments=segments,
            checkpoints=SqliteTranscriptionCheckpointStore(self.engine),
            provider_for=lambda selection: NoAsr(),
            audio_source_for=lambda project_id, media_asset_id: (
                FileSystemInferenceAudioSource(self.root, project_id, media_asset_id)
            ),
            audio_preparer=NoPreparer(),
            clock=lambda: T0 + timedelta(hours=2, seconds=next(ticks)),
            diarization_provider_for=lambda: diarizer,
            assign_speakers=AssignSpeakers(
                transcripts,
                segments,
                SqliteSpeakerRepository(self.engine),
                SqliteSpeakerTurnRepository(self.engine),
            ),
        )


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    engine = create_sqlite_engine((tmp_path / "voz.db").absolute())
    upgrade_to_head(engine)
    project = Project("Clase", created_at=T0)
    SqliteProjectRepository(engine).add(project)
    asset = MediaAsset(project.id, "a" * 64, "tone.wav", 8_044, duration_ms=300)
    SqliteMediaAssetRepository(engine).add(asset)
    job = TranscriptionJob(
        id=uuid4(),
        project_id=project.id,
        media_asset_id=asset.id,
        state=TranscriptionJobState.COMPLETED,
        progress=1.0,
        created_at=T0,
        updated_at=T0,
    )
    SqliteTranscriptionJobRepository(engine).add(job)
    SqliteTranscriptionJobSelectionRepository(engine).add(
        JobSelection(
            job_id=job.id,
            option_id="option-v1-fixture",
            model=DESCRIPTOR,
            execution=None,
            language=None,
            created_at=T0,
            diarization=DiarizationOptions(),
        )
    )
    transcript = Transcript(
        project.id, asset.id, id=transcript_id_for(job.id), created_at=T0
    )
    SqliteTranscriptRepository(engine).add(transcript)
    teacher = Speaker(project.id, "Profesora", "#4e79a7")
    student = Speaker(project.id, "Camila", "#f28e2b")
    speakers = SqliteSpeakerRepository(engine)
    speakers.add(teacher)
    speakers.add(student)
    segments = SqliteSegmentRepository(engine)
    for start, owner in ((0, teacher), (100, teacher), (200, student)):
        segments.add(
            Segment(transcript.id, start, start + 100, f"t{start}", speaker_id=owner.id)
        )
    SqliteSpeakerTurnRepository(engine).replace_for_transcript(
        transcript.id,
        (
            SpeakerTurn(transcript.id, "0", 0, 200, speaker_id=teacher.id),
            SpeakerTurn(transcript.id, "1", 200, 300, speaker_id=student.id),
        ),
    )
    root = tmp_path / "data"
    target = root / "projects" / str(project.id) / "derivatives"
    target.mkdir(parents=True)
    shutil.copyfile(WAV_FIXTURE, target / f"{asset.id}.inference.wav")
    yield World(engine, job, root, teacher, student)
    engine.dispose()


def _names(world: World) -> list[str | None]:
    names = {
        s.id: s.name
        for s in SqliteSpeakerRepository(world.engine).list_by_project(
            world.job.project_id
        )
    }
    return [
        None if s.speaker_id is None else names[s.speaker_id]
        for s in SqliteSegmentRepository(world.engine).list_by_transcript(
            world.transcript_id
        )
    ]


def test_rerun_reopens_the_job_and_keeps_names_by_overlap(world: World) -> None:
    # The new run numbers its clusters differently (swapped labels) and splits
    # the student's stretch; the names must follow the voices, not the labels.
    diarizer = Diarizer(
        DiarizationResult(
            (
                DiarizedTurn(0, 200, "7"),
                DiarizedTurn(200, 250, "3"),
                DiarizedTurn(250, 300, "9"),
            )
        )
    )
    options = DiarizationOptions(SpeakerCountHint(exact=3))

    started = world.use_case().execute(world.transcript_id, options)

    assert started.job.state is TranscriptionJobState.DIARIZING
    assert started.job.id == world.job.id
    assert started.job.error_code is None
    assert started.selection.diarization == options
    finished = world.runner(diarizer).run_job(world.job.id)

    assert finished is not None
    assert finished.state is TranscriptionJobState.COMPLETED
    assert diarizer.options == [options]
    stored = SqliteTranscriptionJobSelectionRepository(world.engine).get(world.job.id)
    assert stored is not None and stored.diarization == options  # still there
    names = _names(world)
    assert names[:2] == ["Profesora", "Profesora"]
    assert names[2] == "Camila"  # 200-250 / 200-300 overlaps the old student 100 %
    speakers = SqliteSpeakerRepository(world.engine).list_by_transcript(
        world.transcript_id
    )
    # The split-off voice (cluster 9) is new: it gets a fresh name, no old one.
    assert {s.name for s in speakers} == {"Profesora", "Camila", "Speaker 3"}


def test_rerun_drops_speakers_nobody_references(world: World) -> None:
    diarizer = Diarizer(DiarizationResult((DiarizedTurn(0, 300, "0"),)))

    world.use_case().execute(
        world.transcript_id, DiarizationOptions(SpeakerCountHint(exact=1))
    )
    world.runner(diarizer).run_job(world.job.id)

    remaining = SqliteSpeakerRepository(world.engine).list_by_project(
        world.job.project_id
    )
    assert [s.name for s in remaining] == ["Profesora"]
    assert _names(world) == ["Profesora"] * 3


def test_failed_rerun_keeps_old_speakers_and_completes(world: World) -> None:
    class Broken(Diarizer):
        def diarize(self, **_: object) -> DiarizationResult:  # type: ignore[override]
            raise RuntimeError("boom")

    world.use_case().execute(world.transcript_id, DiarizationOptions())
    finished = world.runner(Broken(DiarizationResult(()))).run_job(world.job.id)

    assert finished is not None and finished.state is TranscriptionJobState.COMPLETED
    assert _names(world) == ["Profesora", "Profesora", "Camila"]
    selection = SqliteTranscriptionJobSelectionRepository(world.engine).get(
        world.job.id
    )
    assert selection is not None
    assert selection.diarization_error_code == "diarization_provider_failed"


def test_reports_stage_progress(world: World) -> None:
    started = world.use_case().execute(world.transcript_id, DiarizationOptions())

    assert started.job.stage_progress is None
    assert started.job.stage_started_at == T0 + timedelta(hours=1)
    assert started.job.progress == pytest.approx(0.8)


@pytest.mark.parametrize(
    ("availability", "code"),
    [
        (Availability(runtime=False), RediarizeFailureCode.DIARIZATION_UNAVAILABLE),
        (Availability(models=False), RediarizeFailureCode.DIARIZATION_MODELS_MISSING),
    ],
)
def test_refuses_when_diarization_is_missing(
    world: World, availability: Availability, code: RediarizeFailureCode
) -> None:
    with pytest.raises(RediarizeError) as error:
        world.use_case(availability).execute(world.transcript_id, DiarizationOptions())

    assert error.value.code is code
    job = SqliteTranscriptionJobRepository(world.engine).get(world.job.id)
    assert job is not None and job.state is TranscriptionJobState.COMPLETED


def test_refuses_while_another_job_runs(world: World) -> None:
    other = TranscriptionJob.create(
        job_id=uuid4(),
        project_id=world.job.project_id,
        media_asset_id=world.job.media_asset_id,
        now=T0,
    )
    SqliteTranscriptionJobRepository(world.engine).add(other)

    with pytest.raises(RediarizeError) as error:
        world.use_case().execute(world.transcript_id, DiarizationOptions())

    assert error.value.code is RediarizeFailureCode.JOB_ALREADY_ACTIVE


def test_unknown_transcript_and_orphan_transcript(world: World) -> None:
    with pytest.raises(RediarizeError) as error:
        world.use_case().execute(uuid4(), DiarizationOptions())
    assert error.value.code is RediarizeFailureCode.TRANSCRIPT_NOT_FOUND

    orphan = Transcript(world.job.project_id, world.job.media_asset_id)
    SqliteTranscriptRepository(world.engine).add(orphan)
    with pytest.raises(RediarizeError) as error:
        world.use_case().execute(orphan.id, DiarizationOptions())
    assert error.value.code is RediarizeFailureCode.JOB_NOT_FOUND


def _client(
    world: World, availability: Availability | None = None
) -> tuple[httpx.Client, JobRunner]:
    runner = world.runner(
        Diarizer(
            DiarizationResult((DiarizedTurn(0, 200, "5"), DiarizedTurn(200, 300, "6")))
        )
    )
    app = FastAPI()
    app.include_router(
        create_jobs_router(
            cast("CreateTranscriptionJob", None),
            SqliteTranscriptionJobRepository(world.engine),
            SqliteTranscriptionJobSelectionRepository(world.engine),
            SqliteTranscriptRepository(world.engine),
            SqliteSegmentRepository(world.engine),
            runner,
            rediarize=world.use_case(availability),
        )
    )
    return cast(httpx.Client, TestClient(app)), runner  # pyright: ignore[reportUnknownArgumentType]


def test_endpoint_answers_202_with_the_job_and_the_runner_finishes_it(
    world: World,
) -> None:
    client, runner = _client(world)

    response = client.post(
        f"/api/transcripts/{world.transcript_id}/rediarize",
        json={"speakers": {"exact": 2}},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["id"] == str(world.job.id)
    assert body["state"] == "DIARIZING"
    assert body["transcript_id"] == str(world.transcript_id)
    assert body["stage_progress"] is None and "eta_seconds" in body
    assert body["selection"]["diarization"]["speakers"]["exact"] == 2
    runner.run_job(world.job.id)
    done = client.get(f"/api/jobs/{world.job.id}").json()
    assert done["state"] == "COMPLETED" and done["progress"] == 1.0
    assert _names(world) == ["Profesora", "Profesora", "Camila"]


def test_endpoint_translates_failures_and_validates_the_body(world: World) -> None:
    client, _ = _client(world, Availability(models=False))
    url = f"/api/transcripts/{world.transcript_id}/rediarize"

    missing = client.post(url, json={"speakers": {"exact": 2}})
    assert missing.status_code == 409
    assert missing.json()["detail"]["code"] == "diarization_models_missing"
    invalid = client.post(url, json={"speakers": {"exact": 2, "minimum": 1}})
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "diarization_options_invalid"
    unknown = client.post(f"/api/transcripts/{uuid4()}/rediarize", json={})
    assert (unknown.status_code, unknown.json()["detail"]["code"]) == (
        404,
        "transcript_not_found",
    )
    SqliteTranscriptionJobRepository(world.engine).add(
        TranscriptionJob.create(
            job_id=uuid4(),
            project_id=world.job.project_id,
            media_asset_id=world.job.media_asset_id,
            now=T0,
        )
    )
    client, _ = _client(world)
    busy = client.post(url, json={})
    assert (busy.status_code, busy.json()["detail"]["code"]) == (
        409,
        "job_already_active",
    )
