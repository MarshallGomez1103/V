"""Integration coverage for all SQLite repository adapters."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

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
from voz.infrastructure.persistence.database import create_sqlite_engine
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

REPOSITORY_ROOT = Path(__file__).parents[3]
BASE_TIME = datetime(2026, 9, 2, 8, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class Repositories:
    projects: SqliteProjectRepository
    media_assets: SqliteMediaAssetRepository
    transcripts: SqliteTranscriptRepository
    segments: SqliteSegmentRepository
    words: SqliteWordRepository
    speakers: SqliteSpeakerRepository
    speaker_turns: SqliteSpeakerTurnRepository
    jobs: SqliteTranscriptionJobRepository


@dataclass(frozen=True, slots=True)
class MigratedDatabase:
    path: Path
    engine: Engine
    repositories: Repositories


def repositories_for(engine: Engine) -> Repositories:
    return Repositories(
        projects=SqliteProjectRepository(engine),
        media_assets=SqliteMediaAssetRepository(engine),
        transcripts=SqliteTranscriptRepository(engine),
        segments=SqliteSegmentRepository(engine),
        words=SqliteWordRepository(engine),
        speakers=SqliteSpeakerRepository(engine),
        speaker_turns=SqliteSpeakerTurnRepository(engine),
        jobs=SqliteTranscriptionJobRepository(engine),
    )


def migrate_database(path: Path) -> Engine:
    engine = create_sqlite_engine(path)
    config = Config(REPOSITORY_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", str(engine.url))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    return engine


@pytest.fixture
def database(tmp_path: Path) -> Iterator[MigratedDatabase]:
    path = tmp_path / "voz.sqlite3"
    engine = migrate_database(path)
    yield MigratedDatabase(path, engine, repositories_for(engine))
    engine.dispose()


def project(
    name: str,
    *,
    created_at: datetime = BASE_TIME,
    identity: UUID | None = None,
) -> Project:
    return Project(name, id=identity or uuid4(), created_at=created_at)


def media_asset(
    project_id: UUID,
    name: str,
    *,
    created_at: datetime = BASE_TIME,
    identity: UUID | None = None,
) -> MediaAsset:
    return MediaAsset(
        project_id,
        "a" * 64,
        name,
        1_024,
        id=identity or uuid4(),
        media_type="audio/wav",
        duration_ms=5_000,
        created_at=created_at,
    )


def transcript(
    project_id: UUID,
    media_asset_id: UUID,
    *,
    created_at: datetime = BASE_TIME,
    identity: UUID | None = None,
    language: str | None = "es-CO",
) -> Transcript:
    return Transcript(
        project_id,
        media_asset_id,
        id=identity or uuid4(),
        language=language,
        created_at=created_at,
    )


def seed_transcript_graph(
    repositories: Repositories,
) -> tuple[Project, MediaAsset, Transcript]:
    owner = project("Clase")
    asset = media_asset(owner.id, "clase.wav")
    root = transcript(owner.id, asset.id)
    repositories.projects.add(owner)
    repositories.media_assets.add(asset)
    repositories.transcripts.add(root)
    return owner, asset, root


def transcription_job(
    project_id: UUID,
    media_asset_id: UUID,
    *,
    state: TranscriptionJobState = TranscriptionJobState.QUEUED,
    progress: float = 0.0,
    created_at: datetime = BASE_TIME,
    identity: UUID | None = None,
    error_code: str | None = None,
) -> TranscriptionJob:
    if state is TranscriptionJobState.COMPLETED:
        progress = 1.0
    return TranscriptionJob(
        id=identity or uuid4(),
        project_id=project_id,
        media_asset_id=media_asset_id,
        state=state,
        progress=progress,
        created_at=created_at,
        updated_at=created_at,
        error_code=error_code,
    )


def test_project_repository_add_save_get_list_order_and_duplicate(
    database: MigratedDatabase,
) -> None:
    repository = database.repositories.projects
    later = project("Después", created_at=BASE_TIME + timedelta(seconds=1))
    earlier = project("Antes")
    repository.add(later)
    repository.add(earlier)

    assert repository.get(earlier.id) == earlier
    assert repository.get(uuid4()) is None
    assert repository.list_all() == (earlier, later)

    renamed = replace(earlier, name="Antes editado")
    repository.save(renamed)
    assert repository.get(earlier.id) == renamed

    with pytest.raises(IntegrityError):
        repository.add(renamed)


def test_media_asset_repository_add_save_get_filter_order_fk_and_duplicate(
    database: MigratedDatabase,
) -> None:
    repositories = database.repositories
    owner = project("Principal")
    other_owner = project("Otro")
    repositories.projects.add(owner)
    repositories.projects.add(other_owner)
    later = media_asset(
        owner.id,
        "later.wav",
        created_at=BASE_TIME + timedelta(seconds=1),
    )
    earlier = media_asset(owner.id, "earlier.wav")
    foreign = media_asset(other_owner.id, "foreign.wav")
    for asset in (later, earlier, foreign):
        repositories.media_assets.add(asset)

    assert repositories.media_assets.get(earlier.id) == earlier
    assert repositories.media_assets.get(uuid4()) is None
    assert repositories.media_assets.list_by_project(owner.id) == (earlier, later)

    edited = replace(earlier, display_name="edited.wav", duration_ms=6_000)
    repositories.media_assets.save(edited)
    assert repositories.media_assets.get(earlier.id) == edited

    with pytest.raises(IntegrityError):
        repositories.media_assets.add(edited)
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        repositories.media_assets.add(media_asset(uuid4(), "orphan.wav"))


def test_transcript_repository_add_save_get_filters_order_and_duplicate(
    database: MigratedDatabase,
) -> None:
    repositories = database.repositories
    owner = project("Principal")
    other_owner = project("Otro")
    repositories.projects.add(owner)
    repositories.projects.add(other_owner)
    asset = media_asset(owner.id, "clase.wav")
    other_asset = media_asset(other_owner.id, "otra.wav")
    repositories.media_assets.add(asset)
    repositories.media_assets.add(other_asset)
    later = transcript(
        owner.id,
        asset.id,
        created_at=BASE_TIME + timedelta(seconds=1),
        language=None,
    )
    earlier = transcript(owner.id, asset.id)
    foreign = transcript(other_owner.id, other_asset.id)
    for item in (later, earlier, foreign):
        repositories.transcripts.add(item)

    assert repositories.transcripts.get(earlier.id) == earlier
    assert repositories.transcripts.get(uuid4()) is None
    assert repositories.transcripts.list_by_project(owner.id) == (earlier, later)
    assert repositories.transcripts.list_by_media_asset(asset.id) == (earlier, later)

    edited = replace(earlier, language="en-US")
    repositories.transcripts.save(edited)
    assert repositories.transcripts.get(earlier.id) == edited

    with pytest.raises(IntegrityError):
        repositories.transcripts.add(edited)


def test_segment_repository_reconstructs_words_and_saves_aggregate(
    database: MigratedDatabase,
) -> None:
    repositories = database.repositories
    _, _, root = seed_transcript_graph(repositories)
    later = Segment(root.id, 2_000, 3_000, "segundo")
    earlier_id = uuid4()
    first_word = Word(earlier_id, 100, 200, "hola")
    second_word = Word(earlier_id, 300, 450, "mundo")
    earlier = Segment(
        root.id,
        0,
        1_000,
        "primero",
        id=earlier_id,
        words=(first_word, second_word),
    )
    repositories.segments.add(later)
    repositories.segments.add(earlier)

    assert repositories.segments.get(earlier.id) == earlier
    assert repositories.segments.get(uuid4()) is None
    assert repositories.segments.list_by_transcript(root.id) == (earlier, later)

    replacement_word = Word(earlier.id, 500, 750, "editado")
    edited = replace(earlier, text="texto editado", words=(replacement_word,))
    repositories.segments.save(edited)
    assert repositories.segments.get(earlier.id) == edited
    assert repositories.words.get(first_word.id) is None

    with pytest.raises(IntegrityError):
        repositories.segments.add(edited)


def test_word_repository_add_save_get_list_order_and_duplicate(
    database: MigratedDatabase,
) -> None:
    repositories = database.repositories
    _, _, root = seed_transcript_graph(repositories)
    segment = Segment(root.id, 0, 2_000, "segmento")
    repositories.segments.add(segment)
    later = Word(segment.id, 800, 900, "después")
    earlier = Word(segment.id, 100, 200, "antes")
    repositories.words.add(later)
    repositories.words.add(earlier)

    assert repositories.words.get(earlier.id) == earlier
    assert repositories.words.get(uuid4()) is None
    assert repositories.words.list_by_segment(segment.id) == (earlier, later)

    edited = replace(earlier, text="ANTES", end_ms=250)
    repositories.words.save(edited)
    assert repositories.words.get(earlier.id) == edited

    with pytest.raises(IntegrityError):
        repositories.words.add(edited)


def test_speaker_repository_add_save_get_list_order_and_duplicate(
    database: MigratedDatabase,
) -> None:
    repositories = database.repositories
    owner = project("Clase")
    repositories.projects.add(owner)
    later = Speaker(
        owner.id,
        "Estudiante",
        "#222222",
        created_at=BASE_TIME + timedelta(seconds=1),
        updated_at=BASE_TIME + timedelta(seconds=1),
    )
    earlier = Speaker(
        owner.id,
        "SPEAKER_00",
        "#111111",
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
    repositories.speakers.add(later)
    repositories.speakers.add(earlier)

    assert repositories.speakers.get(earlier.id) == earlier
    assert repositories.speakers.get(uuid4()) is None
    assert repositories.speakers.list_by_project(owner.id) == (earlier, later)

    renamed = earlier.rename(
        "Profesor",
        updated_at=BASE_TIME + timedelta(seconds=2),
    )
    repositories.speakers.save(renamed)
    assert repositories.speakers.get(earlier.id) == renamed

    with pytest.raises(IntegrityError):
        repositories.speakers.add(renamed)


def test_speaker_turn_repository_add_save_get_filters_order_and_duplicate(
    database: MigratedDatabase,
) -> None:
    repositories = database.repositories
    owner, _, root = seed_transcript_graph(repositories)
    speaker = Speaker(owner.id, "Profesor", "#123456")
    repositories.speakers.add(speaker)
    later = SpeakerTurn(
        root.id,
        "SPEAKER_01",
        800,
        1_000,
        speaker_id=speaker.id,
    )
    earlier = SpeakerTurn(
        root.id,
        "SPEAKER_00",
        100,
        400,
        speaker_id=speaker.id,
    )
    repositories.speaker_turns.add(later)
    repositories.speaker_turns.add(earlier)

    assert repositories.speaker_turns.get(earlier.id) == earlier
    assert repositories.speaker_turns.get(uuid4()) is None
    assert repositories.speaker_turns.list_by_transcript(root.id) == (
        earlier,
        later,
    )
    assert repositories.speaker_turns.list_by_speaker(speaker.id) == (
        earlier,
        later,
    )

    unassigned = earlier.assign_speaker(None)
    repositories.speaker_turns.save(unassigned)
    assert repositories.speaker_turns.get(earlier.id) == unassigned
    assert repositories.speaker_turns.list_by_speaker(speaker.id) == (later,)

    with pytest.raises(IntegrityError):
        repositories.speaker_turns.add(unassigned)


def test_job_repository_add_save_get_filters_order_recovery_and_duplicate(
    database: MigratedDatabase,
) -> None:
    repositories = database.repositories
    owner = project("Principal")
    other_owner = project("Otro")
    repositories.projects.add(owner)
    repositories.projects.add(other_owner)
    asset = media_asset(owner.id, "clase.wav")
    other_asset = media_asset(other_owner.id, "otra.wav")
    repositories.media_assets.add(asset)
    repositories.media_assets.add(other_asset)
    later = transcription_job(
        owner.id,
        asset.id,
        created_at=BASE_TIME + timedelta(seconds=1),
    )
    earlier = transcription_job(owner.id, asset.id)
    completed = transcription_job(
        owner.id,
        asset.id,
        state=TranscriptionJobState.COMPLETED,
        created_at=BASE_TIME + timedelta(seconds=2),
    )
    foreign = transcription_job(
        other_owner.id,
        other_asset.id,
        created_at=BASE_TIME + timedelta(microseconds=500_000),
    )
    for job in (later, earlier, completed, foreign):
        repositories.jobs.add(job)

    assert repositories.jobs.get(earlier.id) == earlier
    assert repositories.jobs.get(uuid4()) is None
    assert repositories.jobs.list_by_project(owner.id) == (
        earlier,
        later,
        completed,
    )
    assert repositories.jobs.list_by_media_asset(asset.id) == (
        earlier,
        later,
        completed,
    )
    assert repositories.jobs.list_recoverable() == (earlier, foreign, later)

    probing = earlier.transition_to(
        TranscriptionJobState.PROBING,
        at=BASE_TIME + timedelta(seconds=3),
    ).with_progress(0.1, at=BASE_TIME + timedelta(seconds=4))
    repositories.jobs.save(probing)
    assert repositories.jobs.get(earlier.id) == probing

    with pytest.raises(IntegrityError):
        repositories.jobs.add(probing)


def test_project_and_jobs_survive_engine_reopen_with_only_non_terminal_recovery(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "restart" / "voz.sqlite3"
    first_engine = migrate_database(database_path)
    first = repositories_for(first_engine)
    owner = project("Clase recuperable")
    asset = media_asset(owner.id, "larga.wav")
    recoverable = transcription_job(
        owner.id,
        asset.id,
        state=TranscriptionJobState.TRANSCRIBING,
        progress=0.55,
    )
    cancelling = transcription_job(
        owner.id,
        asset.id,
        state=TranscriptionJobState.CANCELLING,
        progress=0.75,
        created_at=BASE_TIME + timedelta(seconds=1),
    )
    terminal_jobs = (
        transcription_job(
            owner.id,
            asset.id,
            state=TranscriptionJobState.COMPLETED,
            created_at=BASE_TIME + timedelta(seconds=2),
        ),
        transcription_job(
            owner.id,
            asset.id,
            state=TranscriptionJobState.FAILED,
            progress=0.2,
            created_at=BASE_TIME + timedelta(seconds=3),
            error_code="ASR_PROVIDER_ERROR",
        ),
        transcription_job(
            owner.id,
            asset.id,
            state=TranscriptionJobState.CANCELLED,
            progress=0.3,
            created_at=BASE_TIME + timedelta(seconds=4),
        ),
    )
    first.projects.add(owner)
    first.media_assets.add(asset)
    for job in (recoverable, cancelling, *terminal_jobs):
        first.jobs.add(job)
    first_engine.dispose()

    reopened_engine = create_sqlite_engine(database_path)
    try:
        reopened = repositories_for(reopened_engine)
        assert reopened.projects.get(owner.id) == owner
        assert reopened.jobs.get(recoverable.id) == recoverable
        assert reopened.jobs.list_recoverable() == (recoverable, cancelling)
        assert {job.state for job in reopened.jobs.list_recoverable()} == {
            TranscriptionJobState.TRANSCRIBING,
            TranscriptionJobState.CANCELLING,
        }
    finally:
        reopened_engine.dispose()
