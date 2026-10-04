"""SQLite read model for the library (a handful of set queries, no N+1)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import Engine, RowMapping, func, select

from voz.application.job_runner import transcript_id_for
from voz.application.ports.library import LibraryEntry, LibraryJob, LibraryMedia
from voz.domain.entities.transcription_job import TranscriptionJobState
from voz.infrastructure.persistence.schema import (
    media_assets,
    projects,
    segments,
    transcription_job_selections,
    transcription_jobs,
    transcripts,
)


def _text(row: RowMapping, key: str) -> str:
    return str(row[key])


def _optional_text(row: RowMapping, key: str) -> str | None:
    value: object = row[key]
    return None if value is None else str(value)


def _when(row: RowMapping, key: str) -> datetime:
    return datetime.fromisoformat(_text(row, key))


class SqliteLibraryReader:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def entries(self) -> Sequence[LibraryEntry]:
        with self._engine.connect() as connection:
            project_rows = connection.execute(select(projects)).mappings().all()
            asset_rows = (
                connection.execute(
                    select(media_assets).order_by(
                        media_assets.c.created_at, media_assets.c.id
                    )
                )
                .mappings()
                .all()
            )
            job_rows = (
                connection.execute(
                    select(
                        transcription_jobs,
                        transcription_job_selections.c.model_id,
                    ).join(
                        transcription_job_selections,
                        transcription_job_selections.c.job_id
                        == transcription_jobs.c.id,
                        isouter=True,
                    )
                )
                .mappings()
                .all()
            )
            latest: dict[str, RowMapping] = {}
            for row in job_rows:
                known = latest.get(_text(row, "project_id"))
                if known is None or (_text(row, "created_at"), _text(row, "id")) > (
                    _text(known, "created_at"),
                    _text(known, "id"),
                ):
                    latest[_text(row, "project_id")] = row
            candidates = [
                str(transcript_id_for(UUID(_text(row, "id"))))
                for row in latest.values()
            ]
            existing = {
                str(row[0])
                for row in connection.execute(
                    select(transcripts.c.id).where(transcripts.c.id.in_(candidates))
                )
            }
            segment_counts = {
                str(row[0]): int(row[1])
                for row in connection.execute(
                    select(segments.c.transcript_id, func.count())
                    .where(segments.c.transcript_id.in_(existing))
                    .group_by(segments.c.transcript_id)
                )
            }
            # Only speakers that own at least one segment: turn-only speakers
            # (a cluster that no segment ended up using) are invisible to the UI.
            speaker_counts = {
                str(row[0]): int(row[1])
                for row in connection.execute(
                    select(
                        segments.c.transcript_id,
                        func.count(segments.c.speaker_id.distinct()),
                    )
                    .where(
                        segments.c.speaker_id.is_not(None),
                        segments.c.transcript_id.in_(existing),
                    )
                    .group_by(segments.c.transcript_id)
                )
            }
        assets_by_id = {_text(row, "id"): row for row in asset_rows}
        first_asset: dict[str, RowMapping] = {}
        for row in asset_rows:
            first_asset.setdefault(_text(row, "project_id"), row)

        entries: list[LibraryEntry] = []
        for project in project_rows:
            project_id = _text(project, "id")
            job: LibraryJob | None = None
            counts = (0, 0)
            asset = first_asset.get(project_id)
            row = latest.get(project_id)
            if row is not None:
                job_id = UUID(_text(row, "id"))
                transcript = str(transcript_id_for(job_id))
                has_transcript = transcript in existing
                raw_progress: object = row["progress"]
                job = LibraryJob(
                    id=job_id,
                    state=TranscriptionJobState(_text(row, "state")),
                    transcript_id=UUID(transcript) if has_transcript else None,
                    model_id=_optional_text(row, "model_id"),
                    progress=float(str(raw_progress)),
                    error_code=_optional_text(row, "error_code"),
                    created_at=_when(row, "created_at"),
                    updated_at=_when(row, "updated_at"),
                )
                asset = assets_by_id.get(_text(row, "media_asset_id"), asset)
                if has_transcript:
                    counts = (
                        speaker_counts.get(transcript, 0),
                        segment_counts.get(transcript, 0),
                    )
            media: LibraryMedia | None = None
            if asset is not None:
                duration = _optional_text(asset, "duration_ms")
                media = LibraryMedia(
                    media_asset_id=UUID(_text(asset, "id")),
                    filename=_text(asset, "display_name"),
                    media_type=_optional_text(asset, "media_type"),
                    duration_ms=None if duration is None else int(duration),
                )
            entries.append(
                LibraryEntry(
                    project_id=UUID(project_id),
                    name=_text(project, "name"),
                    created_at=_when(project, "created_at"),
                    media=media,
                    latest_job=job,
                    speaker_count=counts[0],
                    segment_count=counts[1],
                )
            )
        return tuple(entries)


__all__ = ["SqliteLibraryReader"]
