"""Path-traversal-safe export filenames (S10.09)."""

from __future__ import annotations

import re

_FALLBACK_STEM = "transcript"
_MAX_STEM_LENGTH = 100
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{n}" for n in range(1, 10)}
    | {f"LPT{n}" for n in range(1, 10)}
)
# Control characters (incl. NUL), path separators and Windows-forbidden chars.
_FORBIDDEN = re.compile(r'[\x00-\x1f\x7f/\\<>:"|?*]')
_EXTENSION = re.compile(r"[a-z0-9]{1,16}", re.ASCII)


def safe_export_filename(stem: str, extension: str) -> str:
    """Return ``"<basename>.<extension>"`` that can never escape a directory.

    Only the last path component of ``stem`` is kept; separators, ``..``
    components, control characters, NUL and Windows-forbidden characters are
    removed; the stem is capped at 100 characters; Windows reserved device names
    are prefixed with ``_``; an empty result falls back to ``transcript``.
    """

    normalized_extension = extension.lstrip(".").lower()
    if _EXTENSION.fullmatch(normalized_extension) is None:
        raise ValueError("extension must be 1-16 ASCII letters or digits")

    # ponytail: keep only the final component; "../x" and "C:\\x" both reduce to
    # "x" so no absolute or relative path can survive.
    basename = stem.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _FORBIDDEN.sub("", basename).strip().strip(".").strip()
    cleaned = cleaned[:_MAX_STEM_LENGTH].rstrip(" .") or _FALLBACK_STEM
    if cleaned.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    return f"{cleaned}.{normalized_extension}"


__all__ = ["safe_export_filename"]
