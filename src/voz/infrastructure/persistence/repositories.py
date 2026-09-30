"""Synchronous SQLAlchemy Core repository adapters for SQLite."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    Connection,
    Engine,
    RowMapping,
    Table,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.sql.elements import ColumnElement

from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.project import Project
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.speaker_turn import SpeakerTurn
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.transcription_job import (
    TERMINAL_STATES,
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.domain.entities.word import Word
from voz.infrastructure.persistence.schema import (
    media_assets,
    projects,
    segments,
    speaker_turns,
    speakers,
    transcription_jobs,
    transcripts,
    words,
)


def _text(row: RowMapping, key: str) -> str:
    value = row[key]
    if not isinstance(value, str):
        raise TypeError(f"persisted {key} must be a string")
    return value


def _optional_text(row: RowMapping, key: str) -> str | None:
    value = row[key]
    if value is None or isinstance(value, str):
        return value
    raise TypeError(f"persisted {key} must be a string or null")


def _integer(row: RowMapping, key: str) -> int:
    value = row[key]
    if type(value) is not int:
        raise TypeError(f"persisted {key} must be an integer")
    return value


def _optional_integer(row: RowMapping, key: str) -> int | None:
    value = row[key]
    if value is None:
        return None
    if type(value) is not int:
        raise TypeError(f"persisted {key} must be an integer or null")
    return value


def _real(row: RowMapping, key: str) -> float:
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"persisted {key} must be a real number")
    return float(value)


def _uuid(row: RowMapping, key: str) -> UUID:
    return UUID(_text(row, key))


def _optional_uuid(row: RowMapping, key: str) -> UUID | None:
    value = _optional_text(row, key)
    return None if value is None else UUID(value)


def _timestamp(row: RowMapping, key: str) -> datetime:
    return datetime.fromisoformat(_text(row, key))


def _timestamp_value(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _save(
    engine: Engine,
    table: Table,
    identity: UUID,
    values: Mapping[str, object],
) -> None:
    with engine.begin() as connection:
        result = connection.execute(
            update(table).where(table.c.id == str(identity)).values(values)
        )
        if result.rowcount != 1:
            raise LookupError(f"cannot save missing {table.name} row {identity}")


def _project_values(project: Project) -> dict[str, object]:
    return {
        "id": str(project.id),
        "name": project.name,
        "created_at": _timestamp_value(project.created_at),
    }


def _project_from_row(row: RowMapping) -> Project:
    return Project(
        id=_uuid(row, "id"),
        name=_text(row, "name"),
        created_at=_timestamp(row, "created_at"),
    )


def _media_asset_values(media_asset: MediaAsset) -> dict[str, object]:
    return {
        "id": str(media_asset.id),
        "project_id": str(media_asset.project_id),
        "content_sha256": media_asset.content_sha256,
        "display_name": media_asset.display_name,
        "size_bytes": media_asset.size_bytes,
        "media_type": media_asset.media_type,
        "duration_ms": media_asset.duration_ms,
        "created_at": _timestamp_value(media_asset.created_at),
    }


def _media_asset_from_row(row: RowMapping) -> MediaAsset:
    return MediaAsset(
        id=_uuid(row, "id"),
        project_id=_uuid(row, "project_id"),
        content_sha256=_text(row, "content_sha256"),
        display_name=_text(row, "display_name"),
        size_bytes=_integer(row, "size_bytes"),
        media_type=_optional_text(row, "media_type"),
        duration_ms=_optional_integer(row, "duration_ms"),
        created_at=_timestamp(row, "created_at"),
    )


def _transcript_values(transcript: Transcript) -> dict[str, object]:
    return {
        "id": str(transcript.id),
        "project_id": str(transcript.project_id),
        "media_asset_id": str(transcript.media_asset_id),
        "language": transcript.language,
        "created_at": _timestamp_value(transcript.created_at),
    }


def _transcript_from_row(row: RowMapping) -> Transcript:
    return Transcript(
        id=_uuid(row, "id"),
        project_id=_uuid(row, "project_id"),
        media_asset_id=_uuid(row, "media_asset_id"),
        language=_optional_text(row, "language"),
        created_at=_timestamp(row, "created_at"),
    )


def _word_values(word: Word) -> dict[str, object]:
    return {
        "id": str(word.id),
        "segment_id": str(word.segment_id),
        "start_ms": word.start_ms,
        "end_ms": word.end_ms,
        "text": word.text,
    }


def _word_from_row(row: RowMapping) -> Word:
    return Word(
        id=_uuid(row, "id"),
        segment_id=_uuid(row, "segment_id"),
        start_ms=_integer(row, "start_ms"),
        end_ms=_integer(row, "end_ms"),
        text=_text(row, "text"),
    )


def _segment_values(segment: Segment) -> dict[str, object]:
    return {
        "id": str(segment.id),
        "transcript_id": str(segment.transcript_id),
        "start_ms": segment.start_ms,
        "end_ms": segment.end_ms,
        "text": segment.text,
        "speaker_id": None if segment.speaker_id is None else str(segment.speaker_id),
        "edited": segment.edited,
        "revision": segment.revision,
        "original_text": segment.original_text,
    }


def _segment_from_row(row: RowMapping, segment_words: Sequence[Word]) -> Segment:
    return Segment(
        id=_uuid(row, "id"),
        transcript_id=_uuid(row, "transcript_id"),
        start_ms=_integer(row, "start_ms"),
        end_ms=_integer(row, "end_ms"),
        text=_text(row, "text"),
        words=tuple(segment_words),
        speaker_id=_optional_uuid(row, "speaker_id"),
        edited=bool(row["edited"]),
        revision=_integer(row, "revision"),
        original_text=_optional_text(row, "original_text"),
    )


def _speaker_values(speaker: Speaker) -> dict[str, object]:
    return {
        "id": str(speaker.id),
        "project_id": str(speaker.project_id),
        "name": speaker.name,
        "color": speaker.color,
        "created_at": _timestamp_value(speaker.created_at),
        "updated_at": _timestamp_value(speaker.updated_at),
    }


def _speaker_from_row(row: RowMapping) -> Speaker:
    return Speaker(
        id=_uuid(row, "id"),
        project_id=_uuid(row, "project_id"),
        name=_text(row, "name"),
        color=_text(row, "color"),
        created_at=_timestamp(row, "created_at"),
        updated_at=_timestamp(row, "updated_at"),
    )


def _speaker_turn_values(speaker_turn: SpeakerTurn) -> dict[str, object]:
    return {
        "id": str(speaker_turn.id),
        "transcript_id": str(speaker_turn.transcript_id),
        "cluster_label": speaker_turn.cluster_label,
        "start_ms": speaker_turn.start_ms,
        "end_ms": speaker_turn.end_ms,
        "speaker_id": (
            None if speaker_turn.speaker_id is None else str(speaker_turn.speaker_id)
        ),
    }


def _speaker_turn_from_row(row: RowMapping) -> SpeakerTurn:
    return SpeakerTurn(
        id=_uuid(row, "id"),
        transcript_id=_uuid(row, "transcript_id"),
        cluster_label=_text(row, "cluster_label"),
        start_ms=_integer(row, "start_ms"),
        end_ms=_integer(row, "end_ms"),
        speaker_id=_optional_uuid(row, "speaker_id"),
    )


def _job_values(job: TranscriptionJob) -> dict[str, object]:
    return {
        "id": str(job.id),
        "project_id": str(job.project_id),
        "media_asset_id": str(job.media_asset_id),
        "state": job.state.value,
        "progress": job.progress,
        "created_at": _timestamp_value(job.created_at),
        "updated_at": _timestamp_value(job.updated_at),
        "error_code": job.error_code,
    }


def _job_from_row(row: RowMapping) -> TranscriptionJob:
    return TranscriptionJob(
        id=_uuid(row, "id"),
        project_id=_uuid(row, "project_id"),
        media_asset_id=_uuid(row, "media_asset_id"),
        state=TranscriptionJobState(_text(row, "state")),
        progress=_real(row, "progress"),
        created_at=_timestamp(row, "created_at"),
        updated_at=_timestamp(row, "updated_at"),
        error_code=_optional_text(row, "error_code"),
    )


def _one_or_none(
    engine: Engine,
    table: Table,
    identity: UUID,
) -> RowMapping | None:
    with engine.connect() as connection:
        return (
            connection.execute(select(table).where(table.c.id == str(identity)))
            .mappings()
            .one_or_none()
        )


def _words_for_segments(
    connection: Connection,
    segment_ids: Sequence[str],
) -> dict[str, list[Word]]:
    grouped: dict[str, list[Word]] = defaultdict(list)
    if not segment_ids:
        return grouped
    rows = (
        connection.execute(
            select(words)
            .where(words.c.segment_id.in_(segment_ids))
            .order_by(words.c.start_ms, words.c.end_ms, words.c.id)
        )
        .mappings()
        .all()
    )
    for row in rows:
        grouped[_text(row, "segment_id")].append(_word_from_row(row))
    return grouped


def _validate_word_parent(connection: Connection, word: Word) -> None:
    parent = (
        connection.execute(
            select(segments.c.start_ms, segments.c.end_ms).where(
                segments.c.id == str(word.segment_id)
            )
        )
        .mappings()
        .one_or_none()
    )
    if parent is None:
        raise LookupError(f"cannot persist word for missing segment {word.segment_id}")
    if word.start_ms < _integer(parent, "start_ms") or word.end_ms > _integer(
        parent, "end_ms"
    ):
        raise ValueError("word offsets must remain within segment offsets")


class SqliteProjectRepository:
    """SQLAlchemy Core adapter for projects."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, project: Project) -> None:
        with self._engine.begin() as connection:
            connection.execute(insert(projects).values(_project_values(project)))

    def save(self, project: Project) -> None:
        _save(self._engine, projects, project.id, _project_values(project))

    def get(self, project_id: UUID) -> Project | None:
        row = _one_or_none(self._engine, projects, project_id)
        return None if row is None else _project_from_row(row)

    def list_all(self) -> Sequence[Project]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(projects).order_by(projects.c.created_at, projects.c.id)
                )
                .mappings()
                .all()
            )
        return tuple(_project_from_row(row) for row in rows)


class SqliteMediaAssetRepository:
    """SQLAlchemy Core adapter for path-free media metadata."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, media_asset: MediaAsset) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                insert(media_assets).values(_media_asset_values(media_asset))
            )

    def save(self, media_asset: MediaAsset) -> None:
        _save(
            self._engine,
            media_assets,
            media_asset.id,
            _media_asset_values(media_asset),
        )

    def get(self, media_asset_id: UUID) -> MediaAsset | None:
        row = _one_or_none(self._engine, media_assets, media_asset_id)
        return None if row is None else _media_asset_from_row(row)

    def list_by_project(self, project_id: UUID) -> Sequence[MediaAsset]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(media_assets)
                    .where(media_assets.c.project_id == str(project_id))
                    .order_by(media_assets.c.created_at, media_assets.c.id)
                )
                .mappings()
                .all()
            )
        return tuple(_media_asset_from_row(row) for row in rows)


class SqliteTranscriptRepository:
    """SQLAlchemy Core adapter for transcript roots."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, transcript: Transcript) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                insert(transcripts).values(_transcript_values(transcript))
            )

    def save(self, transcript: Transcript) -> None:
        _save(
            self._engine,
            transcripts,
            transcript.id,
            _transcript_values(transcript),
        )

    def get(self, transcript_id: UUID) -> Transcript | None:
        row = _one_or_none(self._engine, transcripts, transcript_id)
        return None if row is None else _transcript_from_row(row)

    def list_by_project(self, project_id: UUID) -> Sequence[Transcript]:
        return self._list_for(transcripts.c.project_id, project_id)

    def list_by_media_asset(self, media_asset_id: UUID) -> Sequence[Transcript]:
        return self._list_for(transcripts.c.media_asset_id, media_asset_id)

    def _list_for(
        self,
        owner_column: ColumnElement[str],
        owner_id: UUID,
    ) -> Sequence[Transcript]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(transcripts)
                    .where(owner_column == str(owner_id))
                    .order_by(transcripts.c.created_at, transcripts.c.id)
                )
                .mappings()
                .all()
            )
        return tuple(_transcript_from_row(row) for row in rows)


class SqliteSegmentRepository:
    """SQLAlchemy Core adapter that reconstructs segments with their words."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, segment: Segment) -> None:
        with self._engine.begin() as connection:
            connection.execute(insert(segments).values(_segment_values(segment)))
            if segment.words:
                connection.execute(
                    insert(words),
                    [_word_values(word) for word in segment.words],
                )

    def save(self, segment: Segment) -> None:
        with self._engine.begin() as connection:
            result = connection.execute(
                update(segments)
                .where(segments.c.id == str(segment.id))
                .values(_segment_values(segment))
            )
            if result.rowcount != 1:
                raise LookupError(f"cannot save missing segments row {segment.id}")
            connection.execute(
                delete(words).where(words.c.segment_id == str(segment.id))
            )
            if segment.words:
                connection.execute(
                    insert(words),
                    [_word_values(word) for word in segment.words],
                )

    def update_text_if_revision(self, segment: Segment, expected_revision: int) -> bool:
        with self._engine.begin() as connection:
            result = connection.execute(
                update(segments)
                .where(
                    segments.c.id == str(segment.id),
                    segments.c.revision == expected_revision,
                )
                .values(
                    text=segment.text,
                    edited=segment.edited,
                    revision=segment.revision,
                    original_text=segment.original_text,
                )
            )
            return result.rowcount == 1

    def update_speakers(self, assignments: Mapping[UUID, UUID | None]) -> None:
        with self._engine.begin() as connection:
            for segment_id, speaker_id in assignments.items():
                connection.execute(
                    update(segments)
                    .where(segments.c.id == str(segment_id))
                    .values(speaker_id=None if speaker_id is None else str(speaker_id))
                )

    def get(self, segment_id: UUID) -> Segment | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(segments).where(segments.c.id == str(segment_id))
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            grouped_words = _words_for_segments(connection, [str(segment_id)])
            return _segment_from_row(row, grouped_words[str(segment_id)])

    def list_by_transcript(self, transcript_id: UUID) -> Sequence[Segment]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(segments)
                    .where(segments.c.transcript_id == str(transcript_id))
                    .order_by(segments.c.start_ms, segments.c.end_ms, segments.c.id)
                )
                .mappings()
                .all()
            )
            segment_ids = [_text(row, "id") for row in rows]
            grouped_words = _words_for_segments(connection, segment_ids)
        return tuple(
            _segment_from_row(row, grouped_words[_text(row, "id")]) for row in rows
        )


class SqliteWordRepository:
    """SQLAlchemy Core adapter for timed words."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, word: Word) -> None:
        with self._engine.begin() as connection:
            _validate_word_parent(connection, word)
            connection.execute(insert(words).values(_word_values(word)))

    def save(self, word: Word) -> None:
        with self._engine.begin() as connection:
            _validate_word_parent(connection, word)
            result = connection.execute(
                update(words)
                .where(words.c.id == str(word.id))
                .values(_word_values(word))
            )
            if result.rowcount != 1:
                raise LookupError(f"cannot save missing words row {word.id}")

    def get(self, word_id: UUID) -> Word | None:
        row = _one_or_none(self._engine, words, word_id)
        return None if row is None else _word_from_row(row)

    def list_by_segment(self, segment_id: UUID) -> Sequence[Word]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(words)
                    .where(words.c.segment_id == str(segment_id))
                    .order_by(words.c.start_ms, words.c.end_ms, words.c.id)
                )
                .mappings()
                .all()
            )
        return tuple(_word_from_row(row) for row in rows)


class SqliteSpeakerRepository:
    """SQLAlchemy Core adapter for editable project speakers."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, speaker: Speaker) -> None:
        with self._engine.begin() as connection:
            connection.execute(insert(speakers).values(_speaker_values(speaker)))

    def save(self, speaker: Speaker) -> None:
        _save(self._engine, speakers, speaker.id, _speaker_values(speaker))

    def get(self, speaker_id: UUID) -> Speaker | None:
        row = _one_or_none(self._engine, speakers, speaker_id)
        return None if row is None else _speaker_from_row(row)

    def list_by_project(self, project_id: UUID) -> Sequence[Speaker]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(speakers)
                    .where(speakers.c.project_id == str(project_id))
                    .order_by(speakers.c.created_at, speakers.c.id)
                )
                .mappings()
                .all()
            )
        return tuple(_speaker_from_row(row) for row in rows)


class SqliteSpeakerTurnRepository:
    """SQLAlchemy Core adapter for acoustic speaker turns."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, speaker_turn: SpeakerTurn) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                insert(speaker_turns).values(_speaker_turn_values(speaker_turn))
            )

    def save(self, speaker_turn: SpeakerTurn) -> None:
        _save(
            self._engine,
            speaker_turns,
            speaker_turn.id,
            _speaker_turn_values(speaker_turn),
        )

    def replace_for_transcript(
        self,
        transcript_id: UUID,
        turns: Sequence[SpeakerTurn],
    ) -> None:
        if any(turn.transcript_id != transcript_id for turn in turns):
            raise ValueError("every speaker turn must belong to the transcript")
        with self._engine.begin() as connection:
            connection.execute(
                delete(speaker_turns).where(
                    speaker_turns.c.transcript_id == str(transcript_id)
                )
            )
            if turns:
                connection.execute(
                    insert(speaker_turns),
                    [_speaker_turn_values(turn) for turn in turns],
                )

    def get(self, speaker_turn_id: UUID) -> SpeakerTurn | None:
        row = _one_or_none(self._engine, speaker_turns, speaker_turn_id)
        return None if row is None else _speaker_turn_from_row(row)

    def list_by_transcript(self, transcript_id: UUID) -> Sequence[SpeakerTurn]:
        return self._list_for(speaker_turns.c.transcript_id, transcript_id)

    def list_by_speaker(self, speaker_id: UUID) -> Sequence[SpeakerTurn]:
        return self._list_for(speaker_turns.c.speaker_id, speaker_id)

    def _list_for(
        self,
        owner_column: ColumnElement[str],
        owner_id: UUID,
    ) -> Sequence[SpeakerTurn]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(speaker_turns)
                    .where(owner_column == str(owner_id))
                    .order_by(
                        speaker_turns.c.start_ms,
                        speaker_turns.c.end_ms,
                        speaker_turns.c.id,
                    )
                )
                .mappings()
                .all()
            )
        return tuple(_speaker_turn_from_row(row) for row in rows)


class SqliteTranscriptionJobRepository:
    """SQLAlchemy Core adapter for restart-safe transcription jobs."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, job: TranscriptionJob) -> None:
        with self._engine.begin() as connection:
            connection.execute(insert(transcription_jobs).values(_job_values(job)))

    def save(self, job: TranscriptionJob) -> None:
        _save(
            self._engine,
            transcription_jobs,
            job.id,
            _job_values(job),
        )

    def get(self, job_id: UUID) -> TranscriptionJob | None:
        row = _one_or_none(self._engine, transcription_jobs, job_id)
        return None if row is None else _job_from_row(row)

    def list_by_project(self, project_id: UUID) -> Sequence[TranscriptionJob]:
        return self._list_for(transcription_jobs.c.project_id, project_id)

    def list_by_media_asset(
        self,
        media_asset_id: UUID,
    ) -> Sequence[TranscriptionJob]:
        return self._list_for(transcription_jobs.c.media_asset_id, media_asset_id)

    def list_recoverable(self) -> Sequence[TranscriptionJob]:
        terminal_values = tuple(state.value for state in TERMINAL_STATES)
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(transcription_jobs)
                    .where(transcription_jobs.c.state.not_in(terminal_values))
                    .order_by(
                        transcription_jobs.c.created_at,
                        transcription_jobs.c.id,
                    )
                )
                .mappings()
                .all()
            )
        return tuple(_job_from_row(row) for row in rows)

    def _list_for(
        self,
        owner_column: ColumnElement[str],
        owner_id: UUID,
    ) -> Sequence[TranscriptionJob]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(transcription_jobs)
                    .where(owner_column == str(owner_id))
                    .order_by(
                        transcription_jobs.c.created_at,
                        transcription_jobs.c.id,
                    )
                )
                .mappings()
                .all()
            )
        return tuple(_job_from_row(row) for row in rows)


__all__ = [
    "SqliteMediaAssetRepository",
    "SqliteProjectRepository",
    "SqliteSegmentRepository",
    "SqliteSpeakerRepository",
    "SqliteSpeakerTurnRepository",
    "SqliteTranscriptRepository",
    "SqliteTranscriptionJobRepository",
    "SqliteWordRepository",
]
