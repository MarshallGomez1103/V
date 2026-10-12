"""Map an ElevenLabs Scribe JSON payload to canonical transcription types.

Scribe returns flat ``words`` tokens (``word`` / ``spacing`` / ``audio_event``)
with seconds and an optional ``speaker_id``. They become segments split by
speaker, long pauses and sentence-final punctuation, with millisecond offsets
forced to be monotonic (Scribe may report overlapping speech).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Final, cast

from voz.application.ports.transcription import (
    TranscriptionResult,
    TranscriptionSegment,
    TranscriptionWord,
)

PAUSE_SPLIT_MS: Final = 800
_FINAL_PUNCTUATION: Final = (".", "?", "!", "\u2026", "\u3002", "\uff1f", "\uff01")
_CLOSERS: Final = ")]}\"'\u00bb\u201d\u2019"
_LANGUAGE: Final = re.compile(r"[A-Za-z]{2,8}", re.ASCII)
# ponytail: Scribe answers with ISO 639-3; the rest of VOZ uses ISO 639-1 tags.
_ISO_639_3: Final = {
    "spa": "es",
    "eng": "en",
    "por": "pt",
    "fra": "fr",
    "fre": "fr",
    "deu": "de",
    "ger": "de",
    "ita": "it",
    "cat": "ca",
    "nld": "nl",
    "rus": "ru",
    "jpn": "ja",
    "zho": "zh",
    "kor": "ko",
    "ara": "ar",
    "hin": "hi",
    "pol": "pl",
    "tur": "tr",
    "ukr": "uk",
    "swe": "sv",
}


class InvalidScribeResponse(ValueError):
    """The payload does not have the documented Scribe shape."""


@dataclass(frozen=True, slots=True)
class _Word:
    text: str
    start_ms: int
    end_ms: int
    speaker: str | None


# ponytail: whisper_cpp._mapping has the same shape but raises ValueError, not
# InvalidScribeResponse, so the two stay separate.
def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise InvalidScribeResponse("expected an object")
    return cast(dict[str, object], value)


def _milliseconds(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or value < 0
    ):
        raise InvalidScribeResponse("invalid timestamp")
    return round(value * 1000)


def normalize_language(code: object, requested: str | None) -> str | None:
    """Prefer the caller's hint; else map Scribe's ISO 639-3 code to ISO 639-1."""
    if requested is not None:
        return requested
    if not isinstance(code, str) or _LANGUAGE.fullmatch(code) is None:
        return None
    lowered = code.lower()
    return _ISO_639_3.get(lowered, lowered)


def _words(raw_words: object, offset_ms: int) -> list[_Word]:
    if not isinstance(raw_words, list):
        raise InvalidScribeResponse("words must be a list")
    words: list[_Word] = []
    pending = ""
    cursor = 0
    for raw in cast(list[object], raw_words):
        item = _mapping(raw)
        kind = item.get("type", "word")
        text = item.get("text")
        if not isinstance(text, str):
            raise InvalidScribeResponse("token text must be a string")
        if kind == "spacing" or (kind == "word" and text.strip() == ""):
            pending += text if words else ""
            continue
        if kind != "word":
            continue  # audio events are never part of the literal transcript
        start = max(_milliseconds(item.get("start")) + offset_ms, cursor)
        end = max(_milliseconds(item.get("end")) + offset_ms, start + 1)
        cursor = end
        speaker = item.get("speaker_id")
        words.append(
            _Word(
                pending + text,
                start,
                end,
                speaker if isinstance(speaker, str) and speaker else None,
            )
        )
        pending = ""
    return words


def _starts_new_segment(previous: _Word, current: _Word) -> bool:
    return (
        current.speaker != previous.speaker
        or current.start_ms - previous.end_ms > PAUSE_SPLIT_MS
        or previous.text.rstrip(_CLOSERS).endswith(_FINAL_PUNCTUATION)
    )


def _segment(group: list[_Word], with_words: bool) -> TranscriptionSegment:
    return TranscriptionSegment(
        start_ms=group[0].start_ms,
        end_ms=group[-1].end_ms,
        text="".join(word.text for word in group),
        words=(
            tuple(TranscriptionWord(w.start_ms, w.end_ms, w.text) for w in group)
            if with_words
            else ()
        ),
        speaker=group[0].speaker,
    )


def map_scribe_response(
    payload: object,
    *,
    requested_language: str | None = None,
    offset_ms: int = 0,
    with_words: bool = True,
) -> TranscriptionResult:
    """Build the canonical result or raise ``InvalidScribeResponse``."""
    body = _mapping(payload)
    language = normalize_language(body.get("language_code"), requested_language)
    if "words" not in body:
        if body.get("text"):
            raise InvalidScribeResponse("words are missing")
        return TranscriptionResult(segments=(), language=language)
    groups: list[list[_Word]] = []
    for word in _words(body["words"], offset_ms):
        if groups and not _starts_new_segment(groups[-1][-1], word):
            groups[-1].append(word)
        else:
            groups.append([word])
    return TranscriptionResult(
        segments=tuple(_segment(group, with_words) for group in groups),
        language=language,
    )


__all__ = [
    "PAUSE_SPLIT_MS",
    "InvalidScribeResponse",
    "map_scribe_response",
    "normalize_language",
]
