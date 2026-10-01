"""SQLite adapter for atomic ASR chunk checkpoints and job progress."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid5

from sqlalchemy import Engine, RowMapping, insert, select, update

from voz.application.ports.transcription import (
    TranscriptionSegment,
    TranscriptionWord,
)
from voz.application.ports.transcription_checkpoint import TranscriptionCheckpoint
from voz.domain.entities.transcription_job import TranscriptionJob
from voz.infrastructure.persistence.schema import (
    transcription_checkpoints,
    transcription_jobs,
)


def _segment_json(segment: TranscriptionSegment) -> dict[str, object]:
    item: dict[str, object] = {
        "start_ms": segment.start_ms,
        "end_ms": segment.end_ms,
        "text": segment.text,
    }
    if segment.speaker is not None:  # provider-side diarization label
        item["speaker"] = segment.speaker
    for key in ("avg_logprob", "no_speech_prob", "compression_ratio"):
        metric = getattr(segment, key)
        if metric is not None:  # older checkpoints simply lack the keys
            item[key] = metric
    if segment.exceeds_audio:
        item["exceeds_audio"] = True
    if segment.words:  # checkpoints without words keep their original shape
        item["words"] = [
            {
                "start_ms": word.start_ms,
                "end_ms": word.end_ms,
                "text": word.text,
                "probability": word.probability,
            }
            for word in segment.words
        ]
    return item


def _speaker_from_json(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _metric_from_json(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _words_from_json(value: object) -> tuple[TranscriptionWord, ...]:
    if value is None:  # written before word timestamps existed
        return ()
    if not isinstance(value, list):
        raise TypeError("persisted words must be a list")
    words: list[TranscriptionWord] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            raise TypeError("persisted word must be an object")
        values = cast(dict[str, object], item)
        words.append(
            TranscriptionWord(
                start_ms=cast(int, values.get("start_ms")),
                end_ms=cast(int, values.get("end_ms")),
                text=cast(str, values.get("text")),
                probability=cast("float | None", values.get("probability")),
            )
        )
    return tuple(words)


def _segments_json(segments: tuple[TranscriptionSegment, ...]) -> str:
    return json.dumps(
        [_segment_json(segment) for segment in segments],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _segments_from_json(value: object) -> tuple[TranscriptionSegment, ...]:
    if not isinstance(value, str):
        raise TypeError("persisted segments_json must be a string")
    raw: object = json.loads(value)
    if not isinstance(raw, list):
        raise TypeError("persisted segments_json must contain a list")
    segments: list[TranscriptionSegment] = []
    for item in cast(list[object], raw):
        if not isinstance(item, dict):
            raise TypeError("persisted segment must be an object")
        values = cast(dict[str, object], item)
        segments.append(
            TranscriptionSegment(
                start_ms=cast(int, values.get("start_ms")),
                end_ms=cast(int, values.get("end_ms")),
                text=cast(str, values.get("text")),
                words=_words_from_json(values.get("words")),
                speaker=_speaker_from_json(values.get("speaker")),
                avg_logprob=_metric_from_json(values.get("avg_logprob")),
                no_speech_prob=_metric_from_json(values.get("no_speech_prob")),
                compression_ratio=_metric_from_json(values.get("compression_ratio")),
                exceeds_audio=values.get("exceeds_audio") is True,
            )
        )
    return tuple(segments)


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


def _real(row: RowMapping, key: str) -> float:
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"persisted {key} must be a real number")
    return float(value)


def _checkpoint_values(checkpoint: TranscriptionCheckpoint) -> dict[str, object]:
    return {
        "id": str(uuid5(checkpoint.job_id, f"asr-chunk:{checkpoint.chunk_index}")),
        "job_id": str(checkpoint.job_id),
        "chunk_index": checkpoint.chunk_index,
        "process_start_ms": checkpoint.process_start_ms,
        "process_end_ms": checkpoint.process_end_ms,
        "owned_start_ms": checkpoint.owned_start_ms,
        "owned_end_ms": checkpoint.owned_end_ms,
        "provider_id": checkpoint.provider_id,
        "model_id": checkpoint.model_id,
        "model_source": checkpoint.model_source,
        "model_revision": checkpoint.model_revision,
        "requested_language": checkpoint.requested_language,
        "segments_json": _segments_json(checkpoint.segments),
        "language": checkpoint.language,
        "progress": checkpoint.progress,
        "job_progress": checkpoint.job_progress,
        "completed_at": checkpoint.completed_at.astimezone(UTC).isoformat(),
    }


def _job_values(job: TranscriptionJob) -> dict[str, object]:
    return {
        "project_id": str(job.project_id),
        "media_asset_id": str(job.media_asset_id),
        "state": job.state.value,
        "progress": job.progress,
        "created_at": job.created_at.astimezone(UTC).isoformat(),
        "updated_at": job.updated_at.astimezone(UTC).isoformat(),
        "error_code": job.error_code,
    }


def _checkpoint_from_row(row: RowMapping) -> TranscriptionCheckpoint:
    return TranscriptionCheckpoint(
        job_id=UUID(_text(row, "job_id")),
        chunk_index=_integer(row, "chunk_index"),
        process_start_ms=_integer(row, "process_start_ms"),
        process_end_ms=_integer(row, "process_end_ms"),
        owned_start_ms=_integer(row, "owned_start_ms"),
        owned_end_ms=_integer(row, "owned_end_ms"),
        provider_id=_text(row, "provider_id"),
        model_id=_text(row, "model_id"),
        model_source=_optional_text(row, "model_source"),
        model_revision=_optional_text(row, "model_revision"),
        requested_language=_optional_text(row, "requested_language"),
        segments=_segments_from_json(row["segments_json"]),
        language=_optional_text(row, "language"),
        progress=_real(row, "progress"),
        job_progress=_real(row, "job_progress"),
        completed_at=datetime.fromisoformat(_text(row, "completed_at")),
    )


class SqliteTranscriptionCheckpointStore:
    """Atomically confirm a chunk result and its matching job progress."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def commit(
        self,
        checkpoint: TranscriptionCheckpoint,
        job: TranscriptionJob,
    ) -> None:
        if checkpoint.job_id != job.id:
            raise ValueError("checkpoint and job identities must match")
        if checkpoint.job_progress != job.progress:
            raise ValueError("checkpoint job_progress and job progress must match")
        with self._engine.begin() as connection:
            connection.execute(
                insert(transcription_checkpoints).values(_checkpoint_values(checkpoint))
            )
            result = connection.execute(
                update(transcription_jobs)
                .where(transcription_jobs.c.id == str(job.id))
                .values(_job_values(job))
            )
            if result.rowcount != 1:
                raise LookupError(f"cannot checkpoint missing job {job.id}")

    def list_for_job(self, job_id: UUID) -> Sequence[TranscriptionCheckpoint]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(transcription_checkpoints)
                    .where(transcription_checkpoints.c.job_id == str(job_id))
                    .order_by(transcription_checkpoints.c.chunk_index)
                )
                .mappings()
                .all()
            )
        return tuple(_checkpoint_from_row(row) for row in rows)


__all__ = ["SqliteTranscriptionCheckpointStore"]
