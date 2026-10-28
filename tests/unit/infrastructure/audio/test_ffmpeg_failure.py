"""Classification of FFmpeg exit failures."""

from __future__ import annotations

from pathlib import Path

import pytest

from voz.infrastructure.audio.ffmpeg_failure import (
    FfmpegFailure,
    classify_ffmpeg_exit,
)


@pytest.mark.parametrize(
    ("returncode", "stderr", "expected"),
    [
        (
            1,
            "[matroska,webm @ 0x1] EBML header parsing failed\n"
            "Invalid data found when processing input\n",
            FfmpegFailure.MEDIA,
        ),
        (1, "moov atom not found\n", FfmpegFailure.MEDIA),
        (1, "Error while decoding stream #0:1: Invalid data\n", FfmpegFailure.MEDIA),
        (1, "Stream map '0:3' matches no streams.\n", FfmpegFailure.MEDIA),
        (1, "Could not find codec parameters for stream 0\n", FfmpegFailure.MEDIA),
        (1, "Output file does not contain any stream\n", FfmpegFailure.MEDIA),
        (1, "INVALID DATA FOUND WHEN PROCESSING INPUT\n", FfmpegFailure.MEDIA),
        (1, "Disk quota exceeded\n", FfmpegFailure.STORAGE),
        (
            1,
            "Invalid data found when processing input\nNo space left on device\n",
            FfmpegFailure.STORAGE,
        ),
        (
            1,
            "av_interleaved_write_frame(): No space left on device\n",
            FfmpegFailure.STORAGE,
        ),
        (1, "Error writing trailer: Permission denied\n", FfmpegFailure.STORAGE),
        (1, "Read-only file system\n", FfmpegFailure.STORAGE),
        (127, "", FfmpegFailure.TOOL),
        (126, "Permission denied\n", FfmpegFailure.TOOL),
        (-11, "", FfmpegFailure.INTERNAL),
        (-9, "Invalid data found when processing input\n", FfmpegFailure.INTERNAL),
        (1, "", FfmpegFailure.INTERNAL),
        (1, "Unrecognized option 'bogus'.\n", FfmpegFailure.INTERNAL),
    ],
)
def test_exit_is_classified_by_cause(
    returncode: int, stderr: str, expected: FfmpegFailure
) -> None:
    assert classify_ffmpeg_exit(returncode, stderr) is expected


def test_the_stderr_markers_live_only_in_the_classifier() -> None:
    root = Path(__file__).parents[4] / "src" / "voz"
    marker = "invalid data found"

    offenders = sorted(
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if marker in path.read_text(encoding="utf-8").lower()
        and path.name != "ffmpeg_failure.py"
    )

    assert offenders == []
