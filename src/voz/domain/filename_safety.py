"""Single source of truth for characters a display filename may never contain."""

from __future__ import annotations

import unicodedata
from typing import Final

_UNSAFE_BIDI_CLASSES: Final = frozenset(
    {"LRE", "RLE", "LRO", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI"}
)


def has_unsafe_filename_character(name: str) -> bool:
    """Return whether ``name`` has control, format or bidi-override characters."""
    return any(
        unicodedata.category(character) in {"Cc", "Cf"}
        or unicodedata.bidirectional(character) in _UNSAFE_BIDI_CLASSES
        for character in name
    )
