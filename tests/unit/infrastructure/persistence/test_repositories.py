"""Focused tests for SQLAlchemy Core repository adapters."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine

from voz.application.ports.repositories import (
    MediaAssetRepository,
    ProjectRepository,
    SegmentRepository,
    SpeakerRepository,
    SpeakerTurnRepository,
    TranscriptionJobRepository,
    TranscriptRepository,
    WordRepository,
)
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.project import Project
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.speaker_turn import SpeakerTurn
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.domain.entities.word import Word
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteSegmentRepository,
    SqliteSpeakerRepository,
    SqliteSpeakerTurnRepository,
    SqliteTranscriptionJobRepository,
    SqliteTranscriptRepository,
    SqliteWordRepository,
)
from voz.infrastructure.persistence.schema import media_assets, metadata

_NOW = datetime(2026, 9, 2, 12, tzinfo=UTC)
_DIGEST = "a" * 64


@pytest.fixture
def engine() -> Iterator[Engine]:
    database_engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(database_engine)
    yield database_engine
    database_engine.dispose()


def _add_project_media_transcript(
    engine: Engine,
) -> tuple[Project, MediaAsset, Transcript]:
    project = Project("Clase", created_at=_NOW)
    media_asset = MediaAsset(
        project.id,
        _DIGEST,
        "clase.webm",
        10_000,
        media_type="audio/webm",
        duration_ms=60_000,
        created_at=_NOW,
    )
    transcript = Transcript(
        project.id,
        media_asset.id,
        language="es-CO",
        created_at=_NOW,
    )
    SqliteProjectRepository(engine).add(project)
    SqliteMediaAssetRepository(engine).add(media_asset)
    SqliteTranscriptRepository(engine).add(transcript)
    return project, media_asset, transcript


def test_root_repositories_round_trip_and_list_in_stable_order(engine: Engine) -> None:
    project_repository: ProjectRepository = SqliteProjectRepository(engine)
    media_repository: MediaAssetRepository = SqliteMediaAssetRepository(engine)
    transcript_repository: TranscriptRepository = SqliteTranscriptRepository(engine)
    first = Project("Primero", id=UUID(int=1), created_at=_NOW)
    second = Project("Segundo", id=UUID(int=2), created_at=_NOW)

    project_repository.add(second)
    project_repository.add(first)
    assert project_repository.get(first.id) == first
    assert project_repository.get(uuid4()) is None
    assert project_repository.list_all() == (first, second)

    renamed = replace(first, name="Primero editado")
    project_repository.save(renamed)
    assert project_repository.get(first.id) == renamed

    media = MediaAsset(
        first.id,
        _DIGEST,
        "clase.wav",
        123,
        created_at=_NOW,
    )
    media_repository.add(media)
    assert media_repository.get(media.id) == media
    assert media_repository.list_by_project(first.id) == (media,)

    transcript = Transcript(first.id, media.id, created_at=_NOW)
    transcript_repository.add(transcript)
    translated = replace(transcript, language="es")
    transcript_repository.save(translated)
    assert transcript_repository.get(transcript.id) == translated
    assert transcript_repository.list_by_project(first.id) == (translated,)
    assert transcript_repository.list_by_media_asset(media.id) == (translated,)


def test_segment_repository_reconstructs_words_in_timeline_order(
    engine: Engine,
) -> None:
    _, _, transcript = _add_project_media_transcript(engine)
    segment_id = uuid4()
    later_word = Word(segment_id, 500, 900, "mundo")
    earlier_word = Word(segment_id, 0, 400, "Hola")
    segment = Segment(
        transcript.id,
        0,
        1_000,
        "Hola mundo",
        id=segment_id,
        words=(later_word, earlier_word),
    )
    segment_repository: SegmentRepository = SqliteSegmentRepository(engine)
    word_repository: WordRepository = SqliteWordRepository(engine)

    segment_repository.add(segment)

    reconstructed = replace(segment, words=(earlier_word, later_word))
    assert segment_repository.get(segment.id) == reconstructed
    assert segment_repository.list_by_transcript(transcript.id) == (reconstructed,)
    assert word_repository.get(earlier_word.id) == earlier_word
    assert word_repository.list_by_segment(segment.id) == (earlier_word, later_word)

    edited_word = replace(earlier_word, text="Buenas")
    edited_segment = replace(
        segment,
        text="Buenas mundo",
        words=(edited_word,),
    )
    segment_repository.save(edited_segment)
    assert segment_repository.get(segment.id) == edited_segment
    assert word_repository.get(later_word.id) is None


def test_word_repository_rejects_missing_parent_and_out_of_bounds_add(
    engine: Engine,
) -> None:
    _, _, transcript = _add_project_media_transcript(engine)
    segment = Segment(transcript.id, 100, 200, "segmento")
    segment_repository = SqliteSegmentRepository(engine)
    word_repository = SqliteWordRepository(engine)
    segment_repository.add(segment)
    orphan = Word(uuid4(), 100, 150, "huérfana")
    outside = Word(segment.id, 300, 400, "fuera")

    with pytest.raises(LookupError, match="cannot persist word for missing segment"):
        word_repository.add(orphan)
    with pytest.raises(
        ValueError,
        match="word offsets must remain within segment offsets",
    ):
        word_repository.add(outside)

    assert word_repository.get(orphan.id) is None
    assert word_repository.get(outside.id) is None
    assert segment_repository.get(segment.id) == segment


def test_word_repository_failed_save_preserves_previous_snapshot(
    engine: Engine,
) -> None:
    _, _, transcript = _add_project_media_transcript(engine)
    segment = Segment(transcript.id, 100, 200, "segmento")
    segment_repository = SqliteSegmentRepository(engine)
    word_repository = SqliteWordRepository(engine)
    original = Word(segment.id, 120, 150, "válida")
    segment_repository.add(segment)
    word_repository.add(original)
    outside = replace(original, start_ms=300, end_ms=400, text="inválida")

    with pytest.raises(
        ValueError,
        match="word offsets must remain within segment offsets",
    ):
        word_repository.save(outside)

    assert word_repository.get(original.id) == original
    assert segment_repository.get(segment.id) == replace(segment, words=(original,))


def test_speaker_and_turn_repositories_preserve_editable_assignment(
    engine: Engine,
) -> None:
    project, _, transcript = _add_project_media_transcript(engine)
    speaker_repository: SpeakerRepository = SqliteSpeakerRepository(engine)
    turn_repository: SpeakerTurnRepository = SqliteSpeakerTurnRepository(engine)
    speaker = Speaker(
        project.id,
        "Profesor",
        "#123abc",
        created_at=_NOW,
        updated_at=_NOW,
    )
    later_turn = SpeakerTurn(
        transcript.id,
        "SPEAKER_00",
        1_000,
        2_000,
        speaker_id=speaker.id,
    )
    earlier_turn = SpeakerTurn(
        transcript.id,
        "SPEAKER_00",
        0,
        900,
        speaker_id=speaker.id,
    )

    speaker_repository.add(speaker)
    turn_repository.add(later_turn)
    turn_repository.add(earlier_turn)

    assert speaker_repository.get(speaker.id) == speaker
    assert speaker_repository.list_by_project(project.id) == (speaker,)
    assert turn_repository.list_by_transcript(transcript.id) == (
        earlier_turn,
        later_turn,
    )
    assert turn_repository.list_by_speaker(speaker.id) == (earlier_turn, later_turn)

    renamed = speaker.rename("Docente", updated_at=_NOW + timedelta(seconds=1))
    speaker_repository.save(renamed)
    unassigned = earlier_turn.assign_speaker(None)
    turn_repository.save(unassigned)
    assert speaker_repository.get(speaker.id) == renamed
    assert turn_repository.get(earlier_turn.id) == unassigned


def test_job_repository_recovers_only_non_terminal_jobs(engine: Engine) -> None:
    project, media_asset, _ = _add_project_media_transcript(engine)
    repository: TranscriptionJobRepository = SqliteTranscriptionJobRepository(engine)
    recoverable = TranscriptionJob.create(
        job_id=UUID(int=1),
        project_id=project.id,
        media_asset_id=media_asset.id,
        now=_NOW,
    )
    completed = TranscriptionJob(
        id=UUID(int=2),
        project_id=project.id,
        media_asset_id=media_asset.id,
        state=TranscriptionJobState.COMPLETED,
        progress=1.0,
        created_at=_NOW,
        updated_at=_NOW,
    )
    failed = TranscriptionJob(
        id=UUID(int=3),
        project_id=project.id,
        media_asset_id=media_asset.id,
        state=TranscriptionJobState.FAILED,
        progress=0.5,
        created_at=_NOW,
        updated_at=_NOW,
        error_code="ASR_FAILED",
    )
    cancelled = TranscriptionJob(
        id=UUID(int=4),
        project_id=project.id,
        media_asset_id=media_asset.id,
        state=TranscriptionJobState.CANCELLED,
        progress=0.5,
        created_at=_NOW,
        updated_at=_NOW,
    )
    for job in (cancelled, failed, completed, recoverable):
        repository.add(job)

    assert repository.get(recoverable.id) == recoverable
    assert repository.list_recoverable() == (recoverable,)
    assert repository.list_by_project(project.id) == (
        recoverable,
        completed,
        failed,
        cancelled,
    )
    assert repository.list_by_media_asset(media_asset.id) == (
        recoverable,
        completed,
        failed,
        cancelled,
    )

    progressed = recoverable.with_progress(0.25, at=_NOW + timedelta(seconds=1))
    repository.save(progressed)
    assert repository.get(recoverable.id) == progressed


def test_schema_and_adapters_never_persist_host_paths(engine: Engine) -> None:
    assert "path" not in media_assets.c
    assert "source_path" not in media_assets.c
    assert isinstance(SqliteProjectRepository(engine), ProjectRepository)
    assert isinstance(SqliteMediaAssetRepository(engine), MediaAssetRepository)
    assert isinstance(SqliteTranscriptRepository(engine), TranscriptRepository)
    assert isinstance(SqliteSegmentRepository(engine), SegmentRepository)
    assert isinstance(SqliteWordRepository(engine), WordRepository)
    assert isinstance(SqliteSpeakerRepository(engine), SpeakerRepository)
    assert isinstance(SqliteSpeakerTurnRepository(engine), SpeakerTurnRepository)
    assert isinstance(
        SqliteTranscriptionJobRepository(engine),
        TranscriptionJobRepository,
    )


def test_save_rejects_missing_entity(engine: Engine) -> None:
    repository = SqliteProjectRepository(engine)

    with pytest.raises(LookupError, match="cannot save missing"):
        repository.save(Project("No existe", created_at=_NOW))
