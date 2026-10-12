"""SQLite adapters for speech synthesis jobs and their stored audio (ADR-0010)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Engine, RowMapping, delete, insert, select, update

from voz.domain.entities.synthesis_job import SynthesisJob, SynthesisJobState
from voz.domain.entities.synthesis_request import (
    SynthesisOutputFormat,
    SynthesisRequest,
)
from voz.domain.entities.synthesized_audio import SynthesizedAudio
from voz.infrastructure.persistence._rows import (
    row_integer,
    row_optional_text,
    row_real,
    row_text,
)
from voz.infrastructure.persistence.schema import synthesis_jobs, synthesized_audio


def _timestamp_value(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _timestamp(row: RowMapping, key: str) -> datetime:
    return datetime.fromisoformat(row_text(row, key))


def _job_values(job: SynthesisJob) -> dict[str, object]:
    request = job.request
    return {
        "id": str(job.id),
        "state": job.state.value,
        "chunks_done": job.chunks_done,
        "chunks_total": job.chunks_total,
        "created_at": _timestamp_value(job.created_at),
        "updated_at": _timestamp_value(job.updated_at),
        "started_at": (
            None if job.started_at is None else _timestamp_value(job.started_at)
        ),
        "error_code": job.error_code,
        "text": request.text,
        "provider_id": request.provider_id,
        "model_id": request.model_id,
        "model_revision": request.model_revision,
        "voice_id": request.voice_id,
        "language": request.language,
        "speed": request.speed,
        "output_format": request.output_format.value,
    }


def _job_from_row(row: RowMapping) -> SynthesisJob:
    return SynthesisJob(
        id=UUID(row_text(row, "id")),
        request=SynthesisRequest(
            text=row_text(row, "text"),
            provider_id=row_text(row, "provider_id"),
            model_id=row_text(row, "model_id"),
            voice_id=row_text(row, "voice_id"),
            model_revision=row_optional_text(row, "model_revision"),
            language=row_optional_text(row, "language"),
            speed=row_real(row, "speed"),
            output_format=SynthesisOutputFormat(row_text(row, "output_format")),
        ),
        state=SynthesisJobState(row_text(row, "state")),
        chunks_done=row_integer(row, "chunks_done"),
        chunks_total=row_integer(row, "chunks_total"),
        created_at=_timestamp(row, "created_at"),
        updated_at=_timestamp(row, "updated_at"),
        error_code=row_optional_text(row, "error_code"),
        started_at=(
            None if row["started_at"] is None else _timestamp(row, "started_at")
        ),
    )


def _audio_values(audio: SynthesizedAudio) -> dict[str, object]:
    return {
        "job_id": str(audio.job_id),
        "relative_path": audio.relative_path,
        "duration_ms": audio.duration_ms,
        "sample_rate": audio.sample_rate,
        "chunk_count": audio.chunk_count,
        "size_bytes": audio.size_bytes,
        "sha256": audio.sha256,
    }


def _audio_from_row(row: RowMapping) -> SynthesizedAudio:
    return SynthesizedAudio(
        job_id=UUID(row_text(row, "job_id")),
        relative_path=row_text(row, "relative_path"),
        duration_ms=row_integer(row, "duration_ms"),
        sample_rate=row_integer(row, "sample_rate"),
        chunk_count=row_integer(row, "chunk_count"),
        size_bytes=row_integer(row, "size_bytes"),
        sha256=row_text(row, "sha256"),
    )


class SqliteSynthesisJobRepository:
    """SQLAlchemy Core adapter for restart-safe synthesis jobs."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, job: SynthesisJob) -> None:
        with self._engine.begin() as connection:
            connection.execute(insert(synthesis_jobs).values(_job_values(job)))

    def save(self, job: SynthesisJob) -> None:
        # Same strategy as transcription jobs: last writer wins on a whole-row
        # UPDATE by id; the runner serializes writers (the domain rejects
        # backwards timestamps and progress). A missing row is an error.
        with self._engine.begin() as connection:
            result = connection.execute(
                update(synthesis_jobs)
                .where(synthesis_jobs.c.id == str(job.id))
                .values(_job_values(job))
            )
            if result.rowcount != 1:
                raise LookupError(f"cannot save missing synthesis job {job.id}")

    def get(self, job_id: UUID) -> SynthesisJob | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(synthesis_jobs).where(synthesis_jobs.c.id == str(job_id))
                )
                .mappings()
                .one_or_none()
            )
        return None if row is None else _job_from_row(row)

    def list_recent(self, limit: int) -> Sequence[SynthesisJob]:
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(synthesis_jobs)
                    .order_by(
                        synthesis_jobs.c.created_at.desc(), synthesis_jobs.c.id.desc()
                    )
                    .limit(limit)
                )
                .mappings()
                .all()
            )
        return tuple(_job_from_row(row) for row in rows)

    def list_recoverable(self) -> Sequence[SynthesisJob]:
        terminal = tuple(
            state.value for state in SynthesisJobState if state.is_terminal
        )
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(synthesis_jobs)
                    .where(synthesis_jobs.c.state.not_in(terminal))
                    .order_by(synthesis_jobs.c.created_at, synthesis_jobs.c.id)
                )
                .mappings()
                .all()
            )
        return tuple(_job_from_row(row) for row in rows)

    def delete(self, job_id: UUID) -> bool:
        # The audio row goes with the job (ON DELETE CASCADE).
        with self._engine.begin() as connection:
            result = connection.execute(
                delete(synthesis_jobs).where(synthesis_jobs.c.id == str(job_id))
            )
        return result.rowcount == 1


class SqliteSynthesizedAudioRepository:
    """SQLAlchemy Core adapter for the stored audio of completed jobs."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, audio: SynthesizedAudio) -> None:
        with self._engine.begin() as connection:
            connection.execute(insert(synthesized_audio).values(_audio_values(audio)))

    def get_by_job(self, job_id: UUID) -> SynthesizedAudio | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(synthesized_audio).where(
                        synthesized_audio.c.job_id == str(job_id)
                    )
                )
                .mappings()
                .one_or_none()
            )
        return None if row is None else _audio_from_row(row)

    def delete(self, job_id: UUID) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                delete(synthesized_audio).where(
                    synthesized_audio.c.job_id == str(job_id)
                )
            )


__all__ = ["SqliteSynthesisJobRepository", "SqliteSynthesizedAudioRepository"]
