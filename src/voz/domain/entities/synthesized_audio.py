"""The stored result of a synthesis job (ADR-0010)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, cast
from uuid import UUID

from voz.domain.entities._validation import (
    require_non_blank,
    require_positive_int,
    require_uuid,
)

_SHA256_HEX: Final = re.compile(r"[0-9a-f]{64}")


def _require_relative_path(value: object) -> str:
    path = require_non_blank(value, field="relative_path")
    if "\\" in path or ":" in path:
        raise ValueError("relative_path must use POSIX separators and no drive")
    if any(part in ("", ".", "..") for part in path.split("/")):
        raise ValueError("relative_path must stay inside V's synthesis storage")
    return path


@dataclass(frozen=True, slots=True)
class SynthesizedAudio:
    """WAV (PCM16 mono) produced by a job, at the model's native sample rate.

    ``relative_path`` is relative to V's synthesis storage and never absolute,
    so host paths cannot leak through the domain.
    """

    job_id: UUID
    relative_path: str
    duration_ms: int
    sample_rate: int
    chunk_count: int
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        require_uuid(self.job_id, field="job_id")
        object.__setattr__(
            self, "relative_path", _require_relative_path(self.relative_path)
        )
        for name in ("duration_ms", "sample_rate", "chunk_count", "size_bytes"):
            require_positive_int(getattr(self, name), field=name)
        if not isinstance(
            sha := cast(object, self.sha256), str
        ) or not _SHA256_HEX.fullmatch(sha):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
