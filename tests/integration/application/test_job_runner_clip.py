"""A job with a clip transcribes and diarizes only that range of the original."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import wave
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

from sqlalchemy import Engine

from voz.application.assign_speakers import AssignSpeakers
from voz.application.job_runner import JobRunner, transcript_id_for
from voz.application.ports.diarization import (
    DiarizationOptions,
    DiarizationResult,
    DiarizedTurn,
)
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionClip,
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
from voz.infrastructure.inference_audio import FileSystemInferenceAudioSource
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteSegmentRepository,
    SqliteSpeakerRepository,
    SqliteSpeakerTurnRepository,
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

BASE_TIME = datetime(2026, 11, 1, 12, tzinfo=UTC)
AUDIO_MS = 25_000
DESCRIPTOR = ModelDescriptor(
    provider_id="fake-asr",
    model_id="fixture",
    display_name="Fixture",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    source="example/fake-asr",
    revision="f" * 40,
)


def _duration_ms(audio: BinaryIO) -> int:
    with wave.open(audio, "rb") as source:
        return source.getnframes() * 1_000 // source.getframerate()


class Provider:
    """Hears local time: one segment from 0 to 1000 ms in every chunk."""

    provider_id = "fake-asr"

    def __init__(self) -> None:
        self.heard_ms: list[int] = []

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        del cancellation
        assert options.clip is None
        self.heard_ms.append(_duration_ms(audio))
        return TranscriptionResult(
            (TranscriptionSegment(0, 1_000, f"chunk-{len(self.heard_ms)}"),), "es"
        )


class Diarizer:
    provider_id = "fake-diarization"

    def __init__(self, turn: DiarizedTurn) -> None:
        self.turn = turn
        self.heard_ms: list[int] = []

    def diarize(
        self,
        *,
        audio: BinaryIO,
        options: DiarizationOptions,
        cancellation: TranscriptionCancellationToken | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> DiarizationResult:
        self.heard_ms.append(_duration_ms(audio))
        return DiarizationResult((self.turn,))


class RecordingSource:
    """Delegates to the real source and notes every clip it was asked for."""

    def __init__(self, inner: FileSystemInferenceAudioSource) -> None:
        self.inner = inner
        self.clips: list[TranscriptionClip] = []

    def open(
        self, clip: TranscriptionClip | None = None
    ) -> AbstractContextManager[BinaryIO]:
        if clip is not None:  # a bare open only checks that the derivative exists
            self.clips.append(clip)
        return self.inner.open(clip)


class NoPreparer:
    def prepare(self, **_: object) -> None:
        raise AssertionError("the derivative already exists")


@dataclass(slots=True)
class World:
    engine: Engine
    job_id: UUID
    runner: JobRunner
    source: RecordingSource
    provider: Provider
    diarizer: Diarizer
    transcript_id: UUID = field(init=False)

    def __post_init__(self) -> None:
        self.transcript_id = transcript_id_for(self.job_id)


def make_world(
    tmp_path: Path,
    clip: TranscriptionClip | None,
    *,
    diarization: DiarizationOptions | None = None,
    chunk_duration_ms: int = 30 * 60 * 1_000,
    overlap_ms: int = 5_000,
    derivative_ms: int = AUDIO_MS,
) -> World:
    engine = create_sqlite_engine((tmp_path / "voz.db").absolute())
    metadata.create_all(engine)
    project = Project("Demo", created_at=BASE_TIME)
    SqliteProjectRepository(engine).add(project)
    asset = MediaAsset(project.id, "a" * 64, "long.wav", 1, duration_ms=AUDIO_MS)
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
            clip=clip,
        )
    )
    root = tmp_path / "data"
    derivatives = root / "projects" / str(project.id) / "derivatives"
    derivatives.mkdir(parents=True)
    with wave.open(str(derivatives / f"{asset.id}.inference.wav"), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes(bytes(16 * 2 * derivative_ms))
    source = RecordingSource(FileSystemInferenceAudioSource(root, project.id, asset.id))
    provider = Provider()
    diarizer = Diarizer(DiarizedTurn(0, 5_000, "0"))
    ticks = iter(range(1, 10_000))
    transcripts = SqliteTranscriptRepository(engine)
    segments = SqliteSegmentRepository(engine)
    runner = JobRunner(
        jobs=SqliteTranscriptionJobRepository(engine),
        selections=SqliteTranscriptionJobSelectionRepository(engine),
        media_assets=SqliteMediaAssetRepository(engine),
        transcripts=transcripts,
        segments=segments,
        checkpoints=SqliteTranscriptionCheckpointStore(engine),
        provider_for=lambda selection: provider,
        audio_source_for=lambda project_id, media_asset_id: source,
        audio_preparer=NoPreparer(),
        clock=lambda: BASE_TIME + timedelta(seconds=next(ticks)),
        diarization_provider_for=lambda: diarizer,
        assign_speakers=AssignSpeakers(
            transcripts,
            segments,
            SqliteSpeakerRepository(engine),
            SqliteSpeakerTurnRepository(engine),
        ),
        chunk_duration_ms=chunk_duration_ms,
        overlap_ms=overlap_ms,
    )
    return World(engine, job.id, runner, source, provider, diarizer)


def test_clip_job_keeps_original_timeline(tmp_path: Path) -> None:
    world = make_world(
        tmp_path,
        TranscriptionClip(10_000, 20_000),
        chunk_duration_ms=4_000,
        overlap_ms=500,
    )

    finished = world.runner.run_job(world.job_id)

    assert finished is not None and finished.state is TranscriptionJobState.COMPLETED
    stored = SqliteSegmentRepository(world.engine).list_by_transcript(
        world.transcript_id
    )
    assert [(item.start_ms, item.end_ms) for item in stored] == [
        (10_000, 11_000),
        (14_000, 14_500),
        (18_000, 18_500),
    ]
    assert stored[0].start_ms >= 10_000 and stored[-1].end_ms <= 20_000
    # The engine only received audio inside the range.
    assert world.source.clips == [
        TranscriptionClip(10_000, 14_500),
        TranscriptionClip(13_500, 18_500),
        TranscriptionClip(17_500, 20_000),
    ]
    assert world.provider.heard_ms == [4_500, 5_000, 2_500]


def test_job_without_clip_transcribes_the_whole_recording(tmp_path: Path) -> None:
    world = make_world(tmp_path, None)

    finished = world.runner.run_job(world.job_id)

    assert finished is not None and finished.state is TranscriptionJobState.COMPLETED
    assert world.source.clips == [TranscriptionClip(0, AUDIO_MS)]
    assert world.provider.heard_ms == [AUDIO_MS]


def test_clip_diarization_turns_stay_inside_clip(tmp_path: Path) -> None:
    world = make_world(
        tmp_path, TranscriptionClip(10_000, 20_000), diarization=DiarizationOptions()
    )

    finished = world.runner.run_job(world.job_id)

    assert finished is not None and finished.state is TranscriptionJobState.COMPLETED
    assert world.diarizer.heard_ms == [10_000]  # the clip, not the whole file
    turns = SqliteSpeakerTurnRepository(world.engine).list_by_transcript(
        world.transcript_id
    )
    assert [(turn.start_ms, turn.end_ms) for turn in turns] == [(10_000, 15_000)]


def test_clip_up_to_the_duration_tolerates_a_slightly_shorter_derivative(
    tmp_path: Path,
) -> None:
    world = make_world(
        tmp_path, TranscriptionClip(20_000, AUDIO_MS), derivative_ms=AUDIO_MS - 10
    )

    finished = world.runner.run_job(world.job_id)

    assert finished is not None and finished.state is TranscriptionJobState.COMPLETED
    assert world.provider.heard_ms == [4_990]  # clamped to the frames that exist
    stored = SqliteSegmentRepository(world.engine).list_by_transcript(
        world.transcript_id
    )
    assert [(item.start_ms, item.end_ms) for item in stored] == [(20_000, 21_000)]
