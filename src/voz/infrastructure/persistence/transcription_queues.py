"""SQLite adapter for project transcription queues."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import Engine, RowMapping, desc, insert, literal_column, select
from sqlalchemy.sql.elements import ColumnElement

from voz.application.ports.transcription_job_selection import JobSelection
from voz.domain.entities.transcription_job import TranscriptionJob
from voz.domain.entities.transcription_queue import (
    SkippedRecording,
    SkipReason,
    TranscriptionQueue,
)
from voz.infrastructure.persistence._rows import row_text
from voz.infrastructure.persistence.repositories import job_values
from voz.infrastructure.persistence.schema import (
    transcription_job_selections,
    transcription_jobs,
    transcription_queue_items,
    transcription_queues,
)
from voz.infrastructure.persistence.transcription_job_selections import (
    selection_values,
)


def _skipped_json(skipped: tuple[SkippedRecording, ...]) -> str:
    return json.dumps(
        [
            {"media_asset_id": str(item.media_asset_id), "reason": item.reason.value}
            for item in skipped
        ],
        separators=(",", ":"),
    )


def _skipped_from_json(value: str) -> tuple[SkippedRecording, ...]:
    raw: object = json.loads(value)
    if not isinstance(raw, list):
        raise TypeError("persisted skipped_json must be a list")
    entries = cast(list[dict[str, str]], raw)
    return tuple(
        SkippedRecording(UUID(entry["media_asset_id"]), SkipReason(entry["reason"]))
        for entry in entries
    )


def _queue_from_row(row: RowMapping) -> TranscriptionQueue:
    return TranscriptionQueue(
        id=UUID(row_text(row, "id")),
        project_id=UUID(row_text(row, "project_id")),
        created_at=datetime.fromisoformat(row_text(row, "created_at")),
        skipped=_skipped_from_json(row_text(row, "skipped_json")),
    )


class SqliteTranscriptionQueueRepository:
    """One queue row plus one ordinary job (and selection) per item."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(
        self,
        queue: TranscriptionQueue,
        items: Sequence[tuple[TranscriptionJob, JobSelection]],
    ) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                insert(transcription_queues).values(
                    id=str(queue.id),
                    project_id=str(queue.project_id),
                    created_at=queue.created_at.astimezone(UTC).isoformat(),
                    skipped_json=_skipped_json(queue.skipped),
                )
            )
            for position, (job, selection) in enumerate(items):
                connection.execute(insert(transcription_jobs).values(job_values(job)))
                connection.execute(
                    insert(transcription_job_selections).values(
                        selection_values(selection)
                    )
                )
                connection.execute(
                    insert(transcription_queue_items).values(
                        queue_id=str(queue.id), position=position, job_id=str(job.id)
                    )
                )

    def get(self, queue_id: UUID) -> TranscriptionQueue | None:
        return self._one(transcription_queues.c.id == str(queue_id))

    def latest_for_project(self, project_id: UUID) -> TranscriptionQueue | None:
        return self._one(
            transcription_queues.c.project_id == str(project_id), latest=True
        )

    def job_ids(self, queue_id: UUID) -> Sequence[UUID]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(transcription_queue_items.c.job_id)
                .where(transcription_queue_items.c.queue_id == str(queue_id))
                .order_by(transcription_queue_items.c.position)
            ).scalars()
            return [UUID(value) for value in rows]

    def _one(
        self, where: ColumnElement[bool], *, latest: bool = False
    ) -> TranscriptionQueue | None:
        statement = select(transcription_queues).where(where)
        if latest:
            # Queues of one project can share an instant: the last insert wins.
            statement = statement.order_by(
                desc(transcription_queues.c.created_at), desc(literal_column("rowid"))
            )
        with self._engine.connect() as connection:
            row = connection.execute(statement.limit(1)).mappings().one_or_none()
        return None if row is None else _queue_from_row(row)


__all__ = ["SqliteTranscriptionQueueRepository"]
