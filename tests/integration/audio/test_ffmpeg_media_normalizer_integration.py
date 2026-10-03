"""Integration and hostile-boundary tests for the local FFmpeg normalizer."""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from voz.application.ports.media_normalization import (
    MediaNormalizationCancellationToken,
    MediaNormalizationError,
    MediaNormalizationFailureCode,
    MediaNormalizationProgress,
    MediaNormalizationProgressCallback,
)
from voz.application.ports.media_probe import MediaProbeResult
from voz.infrastructure.audio.ffmpeg import FfmpegMediaNormalizer
from voz.infrastructure.audio.ffprobe import FfprobeMediaProbe

MEDIA_FIXTURE = Path("tests/fixtures/media/synthetic-tone.webm").absolute()


class _CallbackAbort(BaseException):
    """Simulate a non-Exception interruption after the child has started."""


class _TrackingNormalizer(FfmpegMediaNormalizer):
    child: subprocess.Popen[str] | None = None

    def _start_process(
        self,
        *,
        source_fd: int,
        temporary_fd: int,
        audio_stream_index: int,
    ) -> subprocess.Popen[str]:
        self.child = super()._start_process(
            source_fd=source_fd,
            temporary_fd=temporary_fd,
            audio_stream_index=audio_stream_index,
        )
        return self.child


class _LateCancellationToken:
    cancelled = False

    def is_cancelled(self) -> bool:
        return self.cancelled


class _TemporarySymlinkSwapNormalizer(FfmpegMediaNormalizer):
    def __init__(self, trusted_root: Path, *, victim: Path) -> None:
        super().__init__(trusted_root)
        self._victim = victim

    def _consume_process(
        self,
        process: subprocess.Popen[str],
        *,
        duration_ms: int,
        on_progress: MediaNormalizationProgressCallback | None,
        cancellation: MediaNormalizationCancellationToken | None,
    ) -> None:
        super()._consume_process(
            process,
            duration_ms=duration_ms,
            on_progress=on_progress,
            cancellation=cancellation,
        )
        temporary = next(self._trusted_root.rglob(".normalize-*.tmp.wav"))
        temporary.unlink()
        temporary.symlink_to(self._victim)


def _probe(source: Path) -> MediaProbeResult:
    with source.open("rb") as opened:
        return FfprobeMediaProbe().probe(opened)


def _assert_no_normalization_temporary(trusted_root: Path) -> None:
    assert not list(trusted_root.rglob(".normalize-*.tmp.wav"))


def _assert_no_ffmpeg_monitor_threads() -> None:
    assert not {
        thread.name
        for thread in threading.enumerate()
        if thread.name.startswith("voz-ffmpeg-")
    }


def _assert_child_pipes_closed(normalizer: _TrackingNormalizer) -> None:
    assert normalizer.child is not None
    assert normalizer.child.stdout is not None
    assert normalizer.child.stderr is not None
    assert normalizer.child.stdout.closed
    assert normalizer.child.stderr.closed


def test_real_ffmpeg_creates_mono_16khz_pcm_without_changing_original(
    tmp_path: Path,
) -> None:
    original_digest = hashlib.sha256(MEDIA_FIXTURE.read_bytes()).hexdigest()
    source_probe = _probe(MEDIA_FIXTURE)
    assert source_probe.duration_ms is not None
    audio_stream = source_probe.audio_streams[0]
    project_id = uuid4()
    media_asset_id = uuid4()
    trusted_root = tmp_path / "media"
    normalizer = _TrackingNormalizer(trusted_root)
    progress: list[MediaNormalizationProgress] = []

    with MEDIA_FIXTURE.open("rb") as original:
        result = normalizer.normalize(
            original=original,
            project_id=project_id,
            media_asset_id=media_asset_id,
            duration_ms=source_probe.duration_ms,
            audio_stream_index=audio_stream.index,
            on_progress=progress.append,
        )

    destination = normalizer.normalized_path_for(project_id, media_asset_id)
    output_probe = _probe(destination)
    assert output_probe.audio_streams[0].codec_name == "pcm_s16le"
    assert output_probe.audio_streams[0].sample_rate_hz == 16_000
    assert output_probe.audio_streams[0].channels == 1
    assert result.bytes_written == destination.stat().st_size
    assert hashlib.sha256(MEDIA_FIXTURE.read_bytes()).hexdigest() == original_digest
    assert progress[0].processed_ms == 0
    assert progress[-1].processed_ms == source_probe.duration_ms
    assert [item.processed_ms for item in progress] == sorted(
        item.processed_ms for item in progress
    )
    _assert_no_normalization_temporary(trusted_root)
    _assert_no_ffmpeg_monitor_threads()
    _assert_child_pipes_closed(normalizer)


def test_callback_base_exception_reaps_child_and_cleans_temporary(
    tmp_path: Path,
) -> None:
    normalizer = _TrackingNormalizer(tmp_path / "media")
    project_id = uuid4()
    media_asset_id = uuid4()

    def interrupt(_progress: MediaNormalizationProgress) -> None:
        raise _CallbackAbort

    with MEDIA_FIXTURE.open("rb") as original, pytest.raises(_CallbackAbort):
        normalizer.normalize(
            original=original,
            project_id=project_id,
            media_asset_id=media_asset_id,
            duration_ms=250,
            audio_stream_index=0,
            on_progress=interrupt,
        )

    assert normalizer.child is not None
    assert normalizer.child.poll() is not None
    assert not normalizer.normalized_path_for(project_id, media_asset_id).exists()
    _assert_no_normalization_temporary(tmp_path / "media")
    _assert_no_ffmpeg_monitor_threads()
    _assert_child_pipes_closed(normalizer)


def test_cancellation_requested_by_completion_progress_does_not_publish(
    tmp_path: Path,
) -> None:
    token = _LateCancellationToken()
    normalizer = _TrackingNormalizer(tmp_path / "media")
    project_id = uuid4()
    media_asset_id = uuid4()

    def cancel_at_completion(progress: MediaNormalizationProgress) -> None:
        if progress.processed_ms == progress.total_ms:
            token.cancelled = True

    with (
        MEDIA_FIXTURE.open("rb") as original,
        pytest.raises(MediaNormalizationError) as captured,
    ):
        normalizer.normalize(
            original=original,
            project_id=project_id,
            media_asset_id=media_asset_id,
            duration_ms=250,
            audio_stream_index=0,
            on_progress=cancel_at_completion,
            cancellation=token,
        )

    assert captured.value.code is MediaNormalizationFailureCode.CANCELLED
    assert not normalizer.normalized_path_for(project_id, media_asset_id).exists()
    _assert_no_normalization_temporary(tmp_path / "media")
    _assert_no_ffmpeg_monitor_threads()
    _assert_child_pipes_closed(normalizer)


@pytest.mark.skipif(os.name == "nt", reason="needs symlinks")
def test_temporary_symlink_swap_is_rejected_without_touching_victim(
    tmp_path: Path,
) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("must remain unchanged", encoding="utf-8")
    normalizer = _TemporarySymlinkSwapNormalizer(
        tmp_path / "media",
        victim=victim,
    )
    project_id = uuid4()
    media_asset_id = uuid4()

    with (
        MEDIA_FIXTURE.open("rb") as original,
        pytest.raises(MediaNormalizationError) as captured,
    ):
        normalizer.normalize(
            original=original,
            project_id=project_id,
            media_asset_id=media_asset_id,
            duration_ms=250,
            audio_stream_index=0,
        )

    assert captured.value.code is MediaNormalizationFailureCode.CORRUPTED_MEDIA
    assert victim.read_text(encoding="utf-8") == "must remain unchanged"
    assert not normalizer.normalized_path_for(project_id, media_asset_id).exists()
    _assert_no_normalization_temporary(tmp_path / "media")
    _assert_no_ffmpeg_monitor_threads()


@pytest.mark.parametrize("symlink_component", ["root", "projects"])
def test_symlinked_storage_components_cannot_escape_trusted_root(
    tmp_path: Path,
    symlink_component: str,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    trusted_root = tmp_path / "media"
    if symlink_component == "root":
        trusted_root.symlink_to(outside, target_is_directory=True)
    else:
        trusted_root.mkdir()
        (trusted_root / "projects").symlink_to(outside, target_is_directory=True)
    normalizer = FfmpegMediaNormalizer(trusted_root)

    with (
        MEDIA_FIXTURE.open("rb") as original,
        pytest.raises(MediaNormalizationError) as captured,
    ):
        normalizer.normalize(
            original=original,
            project_id=uuid4(),
            media_asset_id=uuid4(),
            duration_ms=250,
            audio_stream_index=0,
        )

    assert captured.value.code is MediaNormalizationFailureCode.UNSAFE_DESTINATION
    assert not list(outside.iterdir())
    _assert_no_ffmpeg_monitor_threads()


@pytest.mark.skipif(
    os.name == "nt",
    reason="dir_fd identity check: Windows verifies components by path only "
    "(documented weaker guarantee, docs/install/windows-macos.md)",
)
def test_replaced_trusted_root_identity_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted_root = tmp_path / "media"
    trusted_root.mkdir()
    replacement_root = tmp_path / "replacement"
    replacement_root.mkdir()
    detached_root = tmp_path / "detached"
    original_lstat = Path.lstat
    swapped = False

    def lstat_then_swap(path: Path) -> os.stat_result:
        nonlocal swapped
        result = original_lstat(path)
        if path == trusted_root and not swapped:
            trusted_root.rename(detached_root)
            replacement_root.rename(trusted_root)
            swapped = True
        return result

    monkeypatch.setattr(Path, "lstat", lstat_then_swap)
    normalizer = FfmpegMediaNormalizer(trusted_root)

    with (
        MEDIA_FIXTURE.open("rb") as original,
        pytest.raises(MediaNormalizationError) as captured,
    ):
        normalizer.normalize(
            original=original,
            project_id=uuid4(),
            media_asset_id=uuid4(),
            duration_ms=250,
            audio_stream_index=0,
        )

    assert captured.value.code is MediaNormalizationFailureCode.UNSAFE_DESTINATION
    assert not list(trusted_root.iterdir())
    assert not list(detached_root.iterdir())
    _assert_no_ffmpeg_monitor_threads()


def test_corrupt_media_is_typed_path_safe_and_leaves_no_artifact(
    tmp_path: Path,
) -> None:
    source = tmp_path / "private-course-name.webm"
    source.write_bytes(b"not decodable media")
    trusted_root = tmp_path / "media"
    normalizer = _TrackingNormalizer(trusted_root)
    project_id = uuid4()
    media_asset_id = uuid4()

    with (
        source.open("rb") as original,
        pytest.raises(MediaNormalizationError) as captured,
    ):
        normalizer.normalize(
            original=original,
            project_id=project_id,
            media_asset_id=media_asset_id,
            duration_ms=250,
            audio_stream_index=0,
        )

    assert captured.value.code is MediaNormalizationFailureCode.CORRUPTED_MEDIA
    assert source.name not in str(captured.value)
    assert not normalizer.normalized_path_for(project_id, media_asset_id).exists()
    _assert_no_normalization_temporary(trusted_root)
    _assert_no_ffmpeg_monitor_threads()
    _assert_child_pipes_closed(normalizer)


def test_temporary_fsync_failure_is_io_error_and_does_not_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_fsync = os.fsync

    def fail_regular_file_fsync(file_descriptor: int) -> None:
        if stat.S_ISREG(os.fstat(file_descriptor).st_mode):
            raise OSError("simulated file fsync failure")
        original_fsync(file_descriptor)

    monkeypatch.setattr(os, "fsync", fail_regular_file_fsync)
    normalizer = _TrackingNormalizer(tmp_path / "media")
    project_id = uuid4()
    media_asset_id = uuid4()

    with (
        MEDIA_FIXTURE.open("rb") as original,
        pytest.raises(MediaNormalizationError) as captured,
    ):
        normalizer.normalize(
            original=original,
            project_id=project_id,
            media_asset_id=media_asset_id,
            duration_ms=250,
            audio_stream_index=0,
        )

    assert captured.value.code is MediaNormalizationFailureCode.IO_ERROR
    assert not normalizer.normalized_path_for(project_id, media_asset_id).exists()
    _assert_no_normalization_temporary(tmp_path / "media")
    _assert_no_ffmpeg_monitor_threads()
    _assert_child_pipes_closed(normalizer)


def test_publication_fsync_failure_rolls_back_and_is_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_fsync = os.fsync

    def fail_directory_fsync(file_descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(file_descriptor).st_mode):
            raise OSError("simulated directory fsync failure")
        original_fsync(file_descriptor)

    monkeypatch.setattr(os, "fsync", fail_directory_fsync)
    normalizer = _TrackingNormalizer(tmp_path / "media")
    project_id = uuid4()
    media_asset_id = uuid4()

    with (
        MEDIA_FIXTURE.open("rb") as original,
        pytest.raises(MediaNormalizationError) as captured,
    ):
        normalizer.normalize(
            original=original,
            project_id=project_id,
            media_asset_id=media_asset_id,
            duration_ms=250,
            audio_stream_index=0,
        )

    assert captured.value.code is MediaNormalizationFailureCode.IO_ERROR
    assert not normalizer.normalized_path_for(project_id, media_asset_id).exists()
    assert captured.value.__notes__ == [
        "The failed publication rollback could not be synchronized."
    ]
    _assert_no_normalization_temporary(tmp_path / "media")
    _assert_no_ffmpeg_monitor_threads()
    _assert_child_pipes_closed(normalizer)


def test_temporary_cleanup_failure_is_reported_after_successful_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_unlink = os.unlink

    def fail_temporary_unlink(
        path: str | bytes,
        *,
        dir_fd: int | None = None,
    ) -> None:
        if str(path).startswith(".normalize-"):
            raise OSError("simulated cleanup failure")
        original_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", fail_temporary_unlink)
    trusted_root = tmp_path / "media"
    normalizer = _TrackingNormalizer(trusted_root)
    project_id = uuid4()
    media_asset_id = uuid4()

    with (
        MEDIA_FIXTURE.open("rb") as original,
        pytest.raises(MediaNormalizationError) as captured,
    ):
        normalizer.normalize(
            original=original,
            project_id=project_id,
            media_asset_id=media_asset_id,
            duration_ms=250,
            audio_stream_index=0,
        )

    assert captured.value.code is MediaNormalizationFailureCode.IO_ERROR
    assert normalizer.normalized_path_for(project_id, media_asset_id).exists()
    temporaries = list(trusted_root.rglob(".normalize-*.tmp.wav"))
    assert len(temporaries) == 1
    monkeypatch.undo()
    temporaries[0].unlink()
    _assert_no_ffmpeg_monitor_threads()
    _assert_child_pipes_closed(normalizer)


def test_temporary_cleanup_failure_is_not_allowed_to_hide_primary_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_unlink = os.unlink

    def fail_temporary_unlink(
        path: str | bytes,
        *,
        dir_fd: int | None = None,
    ) -> None:
        if str(path).startswith(".normalize-"):
            raise OSError("simulated cleanup failure")
        original_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", fail_temporary_unlink)
    trusted_root = tmp_path / "media"
    normalizer = _TrackingNormalizer(trusted_root)

    def interrupt(_progress: MediaNormalizationProgress) -> None:
        raise _CallbackAbort

    with (
        MEDIA_FIXTURE.open("rb") as original,
        pytest.raises(_CallbackAbort) as captured,
    ):
        normalizer.normalize(
            original=original,
            project_id=uuid4(),
            media_asset_id=uuid4(),
            duration_ms=250,
            audio_stream_index=0,
            on_progress=interrupt,
        )

    assert captured.value.__notes__ == [
        "Normalization temporary cleanup could not be confirmed."
    ]
    temporaries = list(trusted_root.rglob(".normalize-*.tmp.wav"))
    assert len(temporaries) == 1
    monkeypatch.undo()
    temporaries[0].unlink()
    _assert_no_ffmpeg_monitor_threads()
    _assert_child_pipes_closed(normalizer)


def test_real_ffmpeg_uses_absolute_stream_index_one(tmp_path: Path) -> None:
    source = tmp_path / "video-first.mkv"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=16x16:r=1:d=0.3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=700:duration=0.3:sample_rate=16000",
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c:v",
            "ffv1",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(source),
        ],
        check=True,
    )
    source_probe = _probe(source)
    assert [(stream.index, stream.kind.value) for stream in source_probe.streams] == [
        (0, "video"),
        (1, "audio"),
    ]
    assert source_probe.duration_ms is not None
    normalizer = FfmpegMediaNormalizer(tmp_path / "media")
    project_id = uuid4()
    media_asset_id = uuid4()

    with source.open("rb") as original:
        result = normalizer.normalize(
            original=original,
            project_id=project_id,
            media_asset_id=media_asset_id,
            duration_ms=source_probe.duration_ms,
            audio_stream_index=1,
        )

    destination = normalizer.normalized_path_for(project_id, media_asset_id)
    assert result.bytes_written == destination.stat().st_size
    assert _probe(destination).audio_streams[0].codec_name == "pcm_s16le"
    _assert_no_normalization_temporary(tmp_path / "media")
    _assert_no_ffmpeg_monitor_threads()
