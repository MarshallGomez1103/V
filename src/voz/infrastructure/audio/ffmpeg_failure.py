"""Classify why an FFmpeg process exited unsuccessfully."""

from __future__ import annotations

from enum import StrEnum


class FfmpegFailure(StrEnum):
    """Cause categories, independent of any application error code."""

    MEDIA = "media"
    STORAGE = "storage"
    TOOL = "tool"
    INTERNAL = "internal"


_STORAGE_MARKERS = (
    "no space left",
    "disk quota",
    "read-only file system",
    "permission denied",
)
_MEDIA_MARKERS = (
    "invalid data found",
    "moov atom not found",
    "error while decoding",
    "matches no streams",
    "does not contain any stream",
    "could not find codec parameters",
)
# Shell-style "not executable" / "not found" statuses.
_TOOL_EXIT_CODES = frozenset({126, 127})


def classify_ffmpeg_exit(returncode: int, stderr: str) -> FfmpegFailure:
    """Map a non-zero exit and its stderr tail to a cause; unknown is INTERNAL."""

    if returncode in _TOOL_EXIT_CODES:
        return FfmpegFailure.TOOL
    if returncode < 0:  # killed by a signal: nothing reliable to read from stderr
        return FfmpegFailure.INTERNAL
    text = stderr.lower()
    if any(marker in text for marker in _STORAGE_MARKERS):
        return FfmpegFailure.STORAGE
    if any(marker in text for marker in _MEDIA_MARKERS):
        return FfmpegFailure.MEDIA
    return FfmpegFailure.INTERNAL


__all__ = ["FfmpegFailure", "classify_ffmpeg_exit"]
