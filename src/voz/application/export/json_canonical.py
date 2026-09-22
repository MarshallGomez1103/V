"""Canonical, lossless JSON export and its inverse parser.

The document is the stable interchange format for a literal transcript:
``{"format": "voz.transcript", "version": 1, "transcript": ..., "speakers":
[...], "segments": [...]}``. Rendering is deterministic (sorted keys, ordered
segments, trailing newline) so equal inputs yield byte-identical files.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.word import Word

CANONICAL_FORMAT = "voz.transcript"
CANONICAL_VERSION = 1

_JsonObject = dict[str, object]


class CanonicalJsonError(ValueError):
    """Typed parse failure with a stable ``code`` and a user-safe message."""

    code: str

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class JsonExporter:
    """Render the canonical ``voz.transcript`` JSON document."""

    format_id: str = "json"
    file_extension: str = "json"

    def render(
        self,
        transcript: Transcript,
        segments: Sequence[Segment],
        speakers: Sequence[Speaker] = (),
    ) -> str:
        document: _JsonObject = {
            "format": CANONICAL_FORMAT,
            "version": CANONICAL_VERSION,
            "transcript": {
                "id": str(transcript.id),
                "project_id": str(transcript.project_id),
                "media_asset_id": str(transcript.media_asset_id),
                "language": transcript.language,
                "created_at": transcript.created_at.isoformat(),
            },
            "speakers": [
                {"id": str(speaker.id), "name": speaker.name, "color": speaker.color}
                for speaker in speakers
            ],
            "segments": [
                _segment_to_json(segment)
                for segment in sorted(segments, key=lambda item: item.start_ms)
            ],
        }
        return json.dumps(document, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def _segment_to_json(segment: Segment) -> _JsonObject:
    return {
        "id": str(segment.id),
        "start_ms": segment.start_ms,
        "end_ms": segment.end_ms,
        "text": segment.text,
        "words": [
            {
                "id": str(word.id),
                "start_ms": word.start_ms,
                "end_ms": word.end_ms,
                "text": word.text,
            }
            for word in segment.words
        ],
    }


def parse_canonical_json(
    text: str,
) -> tuple[Transcript, tuple[Segment, ...], tuple[Speaker, ...]]:
    """Rebuild domain entities from a canonical document.

    Raises :class:`CanonicalJsonError` with one of the stable codes
    ``malformed_json``, ``unsupported_format``, ``unsupported_version``,
    ``invalid_structure`` or ``invalid_entity``.
    """
    try:
        raw: object = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CanonicalJsonError(
            "malformed_json", "document is not valid JSON"
        ) from exc
    document = _object(raw, "document")
    if _field(document, "format", "document") != CANONICAL_FORMAT:
        raise CanonicalJsonError(
            "unsupported_format", f"document format must be {CANONICAL_FORMAT!r}"
        )
    if _field(document, "version", "document") != CANONICAL_VERSION:
        raise CanonicalJsonError(
            "unsupported_version",
            f"document version must be {CANONICAL_VERSION}",
        )
    try:
        transcript = _parse_transcript(
            _object(_field(document, "transcript", "document"), "transcript")
        )
        speakers = tuple(
            _parse_speaker(_object(item, f"speakers[{index}]"), transcript, index)
            for index, item in enumerate(
                _array(_field(document, "speakers", "document"), "speakers")
            )
        )
        segments = tuple(
            _parse_segment(_object(item, f"segments[{index}]"), transcript, index)
            for index, item in enumerate(
                _array(_field(document, "segments", "document"), "segments")
            )
        )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, CanonicalJsonError):
            raise
        raise CanonicalJsonError(
            "invalid_entity", "document violates transcript invariants"
        ) from exc
    return transcript, segments, speakers


def _parse_transcript(data: _JsonObject) -> Transcript:
    language = _field(data, "language", "transcript")
    return Transcript(
        _uuid(data, "project_id", "transcript"),
        _uuid(data, "media_asset_id", "transcript"),
        id=_uuid(data, "id", "transcript"),
        language=None if language is None else _string(data, "language", "transcript"),
        created_at=_datetime(data, "created_at", "transcript"),
    )


def _parse_speaker(data: _JsonObject, transcript: Transcript, index: int) -> Speaker:
    path = f"speakers[{index}]"
    # ponytail: project_id and audit timestamps are not part of the document;
    # speakers belong to the transcript's project and get fresh timestamps.
    return Speaker(
        transcript.project_id,
        _string(data, "name", path),
        _string(data, "color", path),
        id=_uuid(data, "id", path),
    )


def _parse_segment(data: _JsonObject, transcript: Transcript, index: int) -> Segment:
    path = f"segments[{index}]"
    segment_id = _uuid(data, "id", path)
    words = tuple(
        _parse_word(_object(item, f"{path}.words[{position}]"), segment_id, position)
        for position, item in enumerate(_array(_field(data, "words", path), "words"))
    )
    return Segment(
        transcript.id,
        _int(data, "start_ms", path),
        _int(data, "end_ms", path),
        _string(data, "text", path),
        id=segment_id,
        words=words,
    )


def _parse_word(data: _JsonObject, segment_id: UUID, index: int) -> Word:
    path = f"words[{index}]"
    return Word(
        segment_id,
        _int(data, "start_ms", path),
        _int(data, "end_ms", path),
        _string(data, "text", path),
        id=_uuid(data, "id", path),
    )


def _invalid(path: str, expectation: str) -> CanonicalJsonError:
    return CanonicalJsonError("invalid_structure", f"{path} must {expectation}")


def _object(value: object, path: str) -> _JsonObject:
    if not isinstance(value, dict):
        raise _invalid(path, "be an object")
    return cast(_JsonObject, value)


def _array(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise _invalid(path, "be an array")
    return cast(list[object], value)


def _field(data: _JsonObject, key: str, path: str) -> object:
    if key not in data:
        raise _invalid(f"{path}.{key}", "be present")
    return data[key]


def _string(data: _JsonObject, key: str, path: str) -> str:
    value = _field(data, key, path)
    if not isinstance(value, str):
        raise _invalid(f"{path}.{key}", "be a string")
    return value


def _int(data: _JsonObject, key: str, path: str) -> int:
    value = _field(data, key, path)
    if type(value) is not int:
        raise _invalid(f"{path}.{key}", "be an integer")
    return value


def _uuid(data: _JsonObject, key: str, path: str) -> UUID:
    try:
        return UUID(_string(data, key, path))
    except ValueError as exc:
        raise _invalid(f"{path}.{key}", "be a UUID") from exc


def _datetime(data: _JsonObject, key: str, path: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(_string(data, key, path))
    except ValueError as exc:
        raise _invalid(f"{path}.{key}", "be an ISO 8601 datetime") from exc
    if parsed.tzinfo is None:
        raise _invalid(f"{path}.{key}", "carry a timezone")
    return parsed
