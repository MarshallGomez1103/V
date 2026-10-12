"""Split long text into ordered, size-bounded chunks for speech synthesis (V2-04).

Pure and stdlib-only. Engines only ever see one chunk (ADR-0010); joining the
audio is the assembler's job (V3-04), this module only plans the text side.

Contract of :func:`plan_text_chunks`:

* empty or whitespace-only text returns ``()`` (not an error: nothing to say);
* ``max_chars < 1`` raises ``ValueError``;
* every chunk is ``text[start:end]`` of the *original* text, trimmed, with
  ``len(chunk.text) <= max_chars`` (single exception: one indivisible grapheme
  cluster longer than ``max_chars``, which is kept whole);
* chunks are in order, never overlap, and the characters between them are
  whitespace only, so no spoken content is lost.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

CHUNK_SILENCE_MS = 200
"""Silence between two chunks of the same paragraph (a short breath)."""

PARAGRAPH_SILENCE_MS = 450
"""Silence between two chunks separated by a blank line."""

_TERMINATORS = frozenset(".!?\u2026\u3002\uff01\uff1f")
_CJK_TERMINATORS = frozenset(
    "\u3002\uff01\uff1f"
)  # end a sentence without a following space
_CLOSERS = frozenset("\"'\u201d\u2019\u00bb)]}\u300d\u300f")
_OPENERS = "\"'\u201c\u2018\u00ab([{\u00bf\u00a1\u300c\u300e"
_PARAGRAPH = re.compile(r"\s*\n\s*\n\s*")
_DOTTED = re.compile(r"(?:\w\.)+\w")  # U.S, a.m, e.g

# ponytail: a small fixed abbreviation list instead of a segmentation model.
# Ceiling: "Plan B. Next" (initial) and "in the U.S. Then" do not split; if real
# text needs better, swap this module's boundary test for a trained segmenter.
_ABBREVIATIONS = frozenset(
    {
        "sr",
        "sra",
        "sres",
        "sras",
        "srta",
        "dr",
        "dra",
        "drs",
        "prof",
        "profa",
        "ing",
        "lic",
    }
    | {
        "ud",
        "uds",
        "vd",
        "vds",
        "vs",
        "p",
        "pp",
        "pág",
        "págs",
        "ej",
        "cap",
        "fig",
        "núm",
    }
    | {"aprox", "mr", "mrs", "ms", "st", "jr", "e.g", "i.e"}
)
# Abbreviations that may also end a sentence: split only before a capital.
_ENDABLE_ABBREVIATIONS = frozenset({"etc"})

_COMMA_LIKE = frozenset(",;\uff0c\u3001\uff1b")
_ZWJ = "\u200d"


@dataclass(frozen=True, slots=True)
class TextChunk:
    """One piece of the input: ``text == original[start:end]``."""

    index: int
    text: str
    start: int
    end: int


def silence_gap_ms(gap_text: str) -> int:
    """Silence to insert between two chunks; ``gap_text`` is the original text
    between them (``original[a.end:b.start]``). A blank line pauses longer."""
    return PARAGRAPH_SILENCE_MS if _PARAGRAPH.fullmatch(gap_text) else CHUNK_SILENCE_MS


def plan_text_chunks(text: str, *, max_chars: int) -> tuple[TextChunk, ...]:
    """Plan the chunks of ``text``; see the module docstring for the contract."""
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1")
    pieces: list[tuple[int, int]] = []
    for start, end in _sentence_spans(text):
        pieces.extend(_split_long(text, start, end, max_chars))
    return tuple(
        TextChunk(i, text[s:e], s, e)
        for i, (s, e) in enumerate(_pack(pieces, max_chars))
    )


def _pack(pieces: list[tuple[int, int]], max_chars: int) -> list[tuple[int, int]]:
    """Greedily join consecutive pieces while the joined span fits."""
    packed: list[tuple[int, int]] = []
    for start, end in pieces:
        if packed and end - packed[-1][0] <= max_chars:
            packed[-1] = (packed[-1][0], end)
        else:
            packed.append((start, end))
    return packed


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    n = len(text)
    start: int | None = None
    last_content = 0  # end of the last non-space character of the open sentence
    i = 0
    while i < n:
        c = text[i]
        if start is None:
            if c.isspace():
                i += 1
                continue
            start = i
        if c.isspace():
            m = _PARAGRAPH.match(text, i)
            if m:
                spans.append((start, last_content))
                start = None
                i = m.end()
                continue
            i += 1
            continue
        if c in _TERMINATORS:
            j = i
            while j < n and (text[j] in _TERMINATORS or text[j] in _CLOSERS):
                j += 1
            last_content = j
            run = text[i:j]
            at_boundary = (
                j == n or text[j].isspace() or any(t in _CJK_TERMINATORS for t in run)
            )
            if at_boundary and not (run == "." and _is_abbreviation(text, i, j)):
                spans.append((start, j))
                start = None
            i = j
            continue
        last_content = i + 1
        i += 1
    if start is not None:
        spans.append((start, last_content))
    return spans


def _is_abbreviation(text: str, dot: int, after: int) -> bool:
    """Is the period at ``text[dot]`` part of an abbreviation, not a sentence end?"""
    k = dot
    while k > 0 and not text[k - 1].isspace():
        k -= 1
    token = text[k:dot].lstrip(_OPENERS)
    if len(token) == 1 and token.isalpha() and token.isupper():
        return True  # an initial: "A. Gomez"
    low = token.lower()
    if low in _ABBREVIATIONS or (_DOTTED.fullmatch(token) and "." in token):
        return True
    if low in _ENDABLE_ABBREVIATIONS:
        rest = text[after:].lstrip()
        return bool(rest) and not rest[0].isupper()
    return False


def _split_long(
    text: str, start: int, end: int, max_chars: int
) -> list[tuple[int, int]]:
    """Cut one sentence that exceeds ``max_chars`` into pieces that fit."""
    out: list[tuple[int, int]] = []
    pos = start
    while end - pos > max_chars:
        cut = _cut_point(text, pos, end, max_chars)
        piece_end = pos + len(text[pos:cut].rstrip())
        out.append((pos, piece_end))
        pos = cut
        while pos < end and text[pos].isspace():
            pos += 1
    if pos < end:
        out.append((pos, end))
    return out


def _cut_point(text: str, pos: int, end: int, max_chars: int) -> int:
    window_end = pos + max_chars
    comma = max(
        (i for i in range(pos, window_end) if text[i] in _COMMA_LIKE), default=-1
    )
    if comma >= pos + max_chars // 2:  # a comma near the start would leave crumbs
        return comma + 1
    space = max(
        (i for i in range(pos + 1, min(window_end + 1, end)) if text[i].isspace()),
        default=-1,
    )
    if space > pos:
        return space
    if comma >= pos:
        return comma + 1
    return _grapheme_safe_cut(text, pos, end, window_end)


def _grapheme_safe_cut(text: str, pos: int, end: int, cut: int) -> int:
    """Hard cut near ``cut`` that never separates a combining mark, variation
    selector or ZWJ sequence from its base (backs off; moves on if it must)."""
    c = cut
    while c > pos and not _can_cut_before(text, c):
        c -= 1
    if c > pos:
        return c
    c = cut + 1
    while c < end and not _can_cut_before(text, c):
        c += 1
    return min(c, end)


def _can_cut_before(text: str, i: int) -> bool:
    ch = text[i]
    if ch == _ZWJ or text[i - 1] == _ZWJ:
        return False
    if unicodedata.category(ch) in ("Mn", "Me", "Mc"):
        return False
    return not "\U0001f3fb" <= ch <= "\U0001f3ff"  # emoji skin-tone modifiers
