"""FFmpeg adapter for safe, cancellable audio normalization."""

from __future__ import annotations

import os
import queue
import stat
import subprocess
import sys
import threading
import wave
from collections import deque
from contextlib import suppress
from pathlib import Path
from typing import IO, BinaryIO
from uuid import UUID, uuid4

from voz.application.ports.media_normalization import (
    MediaNormalizationCancellationToken,
    MediaNormalizationError,
    MediaNormalizationFailureCode,
    MediaNormalizationProgress,
    MediaNormalizationProgressCallback,
    NormalizedAudio,
)
from voz.infrastructure._payload import require_uuid
from voz.infrastructure.audio.ffmpeg_failure import (
    FfmpegFailure,
    classify_ffmpeg_exit,
)
from voz.infrastructure.audio.media_args import (
    NO_WINDOW,
    ffmpeg_input_arguments,
    ffmpeg_output_arguments,
)
from voz.infrastructure.child_env import child_environment
from voz.infrastructure.safe_fs import DirectoryHandle, open_directory_chain

_SAMPLE_RATE_HZ = 16_000
_CHANNELS = 1
_SAMPLE_WIDTH_BYTES = 2
_PROGRESS_PREFIX = "out_time_us="
_STREAM_END = object()
_STDERR_TAIL_CHARS = 4096


class FfmpegMediaNormalizer:
    """Produce complete PCM WAV derivatives below a trusted storage root."""

    def __init__(
        self,
        trusted_root: Path,
        *,
        executable: str = "ffmpeg",
        cancellation_poll_seconds: float = 0.05,
        terminate_grace_seconds: float = 1.0,
    ) -> None:
        if not executable.strip():
            raise ValueError("executable must not be blank")
        if (
            isinstance(cancellation_poll_seconds, bool)
            or cancellation_poll_seconds <= 0
        ):
            raise ValueError("cancellation_poll_seconds must be positive")
        if isinstance(terminate_grace_seconds, bool) or terminate_grace_seconds <= 0:
            raise ValueError("terminate_grace_seconds must be positive")
        self._trusted_root = Path(trusted_root).absolute()
        self._executable = executable
        self._cancellation_poll_seconds = cancellation_poll_seconds
        self._terminate_grace_seconds = terminate_grace_seconds

    def normalize(
        self,
        *,
        original: BinaryIO,
        project_id: UUID,
        media_asset_id: UUID,
        duration_ms: int,
        audio_stream_index: int,
        on_progress: MediaNormalizationProgressCallback | None = None,
        cancellation: MediaNormalizationCancellationToken | None = None,
    ) -> NormalizedAudio:
        """Run FFmpeg through inherited descriptors and publish exactly once."""
        require_uuid(project_id, field="project_id")
        require_uuid(media_asset_id, field="media_asset_id")
        if type(duration_ms) is not int or duration_ms <= 0:
            raise ValueError("duration_ms must be a positive integer")
        if type(audio_stream_index) is not int or audio_stream_index < 0:
            raise ValueError("audio_stream_index must be a non-negative integer")

        source_fd = self._source_file_descriptor(original)
        directory: DirectoryHandle | None = None
        temporary_fd: int | None = None
        temporary_name: str | None = None
        process: subprocess.Popen[str] | None = None
        try:
            directory = self._open_derivatives_directory(project_id)
            destination_name = f"{media_asset_id}.inference.wav"
            self._reject_existing_destination(directory, destination_name)
            if self._is_cancelled(cancellation):
                raise self._cancelled_error()

            temporary_name, temporary_fd = self._create_temporary(directory)
            temporary_stat = os.fstat(temporary_fd)
            process = self._start_process(
                source_fd=source_fd,
                temporary_fd=temporary_fd,
                audio_stream_index=audio_stream_index,
            )
            self._consume_process(
                process,
                duration_ms=duration_ms,
                on_progress=on_progress,
                cancellation=cancellation,
            )
            bytes_written = self._validate_and_sync_output(
                temporary_fd=temporary_fd,
                directory=directory,
                temporary_name=temporary_name,
                expected_stat=temporary_stat,
            )
            if self._is_cancelled(cancellation):
                raise self._cancelled_error()
            self._publish_without_replacement(
                directory=directory,
                temporary_name=temporary_name,
                destination_name=destination_name,
                expected_stat=temporary_stat,
            )
            return NormalizedAudio(bytes_written=bytes_written)
        except MediaNormalizationError:
            raise
        except OSError as error:
            raise MediaNormalizationError(
                MediaNormalizationFailureCode.IO_ERROR,
                "The normalized audio could not be stored.",
            ) from error
        finally:
            active_error = sys.exception()
            cleanup_error: MediaNormalizationError | None = None
            if process is not None and process.poll() is None:
                self._stop_process(process)
            if temporary_fd is not None:
                os.close(temporary_fd)
            if directory is not None:
                if temporary_name is not None:
                    try:
                        self._remove_temporary(directory, temporary_name)
                    except MediaNormalizationError as error:
                        cleanup_error = error
                directory.close()
            if cleanup_error is not None:
                if active_error is None:
                    raise cleanup_error
                active_error.add_note(cleanup_error.user_message)

    def normalized_path_for(self, project_id: UUID, media_asset_id: UUID) -> Path:
        """Resolve an infrastructure-only derivative path for verification/playback."""
        require_uuid(project_id, field="project_id")
        require_uuid(media_asset_id, field="media_asset_id")
        return (
            self._trusted_root
            / "projects"
            / str(project_id)
            / "derivatives"
            / f"{media_asset_id}.inference.wav"
        )

    def _start_process(
        self,
        *,
        source_fd: int,
        temporary_fd: int,
        audio_stream_index: int,
    ) -> subprocess.Popen[str]:
        source_arguments, source_inherit = ffmpeg_input_arguments(source_fd)
        output_arguments, output_inherit = ffmpeg_output_arguments(temporary_fd)
        command = [
            self._executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-progress",
            "pipe:1",
            "-nostats",
            *source_arguments,
            "-map",
            f"0:{audio_stream_index}",
            "-vn",
            "-ac",
            str(_CHANNELS),
            "-ar",
            str(_SAMPLE_RATE_HZ),
            "-c:a",
            "pcm_s16le",
            "-f",
            "wav",
            "-y",
            *output_arguments,
        ]
        try:
            return subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                close_fds=True,
                pass_fds=(*source_inherit, *output_inherit),
                creationflags=NO_WINDOW,
                env=child_environment(),
            )
        except FileNotFoundError as error:
            raise MediaNormalizationError(
                MediaNormalizationFailureCode.TOOL_UNAVAILABLE,
                "The audio normalization tool is not installed.",
            ) from error
        except OSError as error:
            raise MediaNormalizationError(
                MediaNormalizationFailureCode.TOOL_UNAVAILABLE,
                "The audio normalization tool could not be started.",
            ) from error

    def _consume_process(
        self,
        process: subprocess.Popen[str],
        *,
        duration_ms: int,
        on_progress: MediaNormalizationProgressCallback | None,
        cancellation: MediaNormalizationCancellationToken | None,
    ) -> None:
        if process.stdout is None or process.stderr is None:
            self._stop_process(process)
            self._close_process_pipes(process)
            raise MediaNormalizationError(
                MediaNormalizationFailureCode.PROCESS_FAILED,
                "Audio normalization could not be monitored.",
            )

        progress_lines: queue.Queue[str | object] = queue.Queue()
        stdout_thread = threading.Thread(
            target=self._pump_progress,
            args=(process.stdout, progress_lines),
            name="voz-ffmpeg-progress",
            daemon=True,
        )
        stderr_tail: deque[str] = deque()
        stderr_thread = threading.Thread(
            target=self._drain_stream,
            args=(process.stderr, stderr_tail),
            name="voz-ffmpeg-stderr",
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        last_processed_ms = -1
        try:
            last_processed_ms = self._report_progress(
                processed_ms=0,
                duration_ms=duration_ms,
                previous_ms=last_processed_ms,
                on_progress=on_progress,
            )
            stdout_finished = False
            while not stdout_finished or process.poll() is None:
                if self._is_cancelled(cancellation):
                    raise self._cancelled_error()
                try:
                    item = progress_lines.get(timeout=self._cancellation_poll_seconds)
                except queue.Empty:
                    continue
                if item is _STREAM_END:
                    stdout_finished = True
                elif isinstance(item, str):
                    processed_ms = self._parse_processed_ms(item, duration_ms)
                    if processed_ms is not None:
                        last_processed_ms = self._report_progress(
                            processed_ms=processed_ms,
                            duration_ms=duration_ms,
                            previous_ms=last_processed_ms,
                            on_progress=on_progress,
                        )

            returncode = process.wait()
            if returncode != 0:
                # The pump may still be flushing; only its bounded tail is read.
                stderr_thread.join(timeout=self._terminate_grace_seconds)
                raise self._exit_error(returncode, "".join(stderr_tail))
            self._report_progress(
                processed_ms=duration_ms,
                duration_ms=duration_ms,
                previous_ms=last_processed_ms,
                on_progress=on_progress,
            )
        except BaseException:
            if process.poll() is None:
                self._stop_process(process)
            raise
        finally:
            if process.poll() is None:
                self._stop_process(process)
            stdout_thread.join(timeout=self._terminate_grace_seconds)
            stderr_thread.join(timeout=self._terminate_grace_seconds)
            self._close_process_pipes(process)
            if stdout_thread.is_alive():
                stdout_thread.join(timeout=self._terminate_grace_seconds)
            if stderr_thread.is_alive():
                stderr_thread.join(timeout=self._terminate_grace_seconds)

    @staticmethod
    def _pump_progress(
        stream: IO[str],
        destination: queue.Queue[str | object],
    ) -> None:
        try:
            try:
                for line in stream:
                    destination.put(line)
            except (OSError, ValueError):
                pass
        finally:
            destination.put(_STREAM_END)

    @staticmethod
    def _drain_stream(stream: IO[str], tail: deque[str]) -> None:
        # Only used to classify the exit; never shown or logged.
        kept = 0
        try:
            for line in stream:
                tail.append(line)
                kept += len(line)
                while kept > _STDERR_TAIL_CHARS and len(tail) > 1:
                    kept -= len(tail.popleft())
        except (OSError, ValueError):
            pass

    @staticmethod
    def _close_process_pipes(process: subprocess.Popen[str]) -> None:
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                with suppress(OSError, ValueError):
                    stream.close()

    @staticmethod
    def _parse_processed_ms(line: str, duration_ms: int) -> int | None:
        if not line.startswith(_PROGRESS_PREFIX):
            return None
        raw_microseconds = line.removeprefix(_PROGRESS_PREFIX).strip()
        if not raw_microseconds.isascii() or not raw_microseconds.isdigit():
            return None
        return min(int(raw_microseconds) // 1000, duration_ms)

    @staticmethod
    def _report_progress(
        *,
        processed_ms: int,
        duration_ms: int,
        previous_ms: int,
        on_progress: MediaNormalizationProgressCallback | None,
    ) -> int:
        if processed_ms <= previous_ms:
            return previous_ms
        if on_progress is not None:
            on_progress(
                MediaNormalizationProgress(
                    processed_ms=processed_ms,
                    total_ms=duration_ms,
                )
            )
        return processed_ms

    def _stop_process(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        with suppress(OSError):
            process.terminate()
        try:
            process.wait(timeout=self._terminate_grace_seconds)
            return
        except subprocess.TimeoutExpired:
            pass
        with suppress(OSError):
            process.kill()
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=self._terminate_grace_seconds)

    def _open_derivatives_directory(self, project_id: UUID) -> DirectoryHandle:
        try:
            return open_directory_chain(
                self._trusted_root,
                ("projects", str(project_id), "derivatives"),
                create=True,
            )
        except OSError as error:
            raise MediaNormalizationError(
                MediaNormalizationFailureCode.UNSAFE_DESTINATION,
                "The configured derivative storage path is unsafe.",
            ) from error

    @staticmethod
    def _create_temporary(directory: DirectoryHandle) -> tuple[str, int]:
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0)
        for _ in range(10):
            name = f".normalize-{uuid4()}.tmp.wav"
            try:
                return name, directory.open_file(name, flags, 0o600)
            except FileExistsError:
                continue
        raise MediaNormalizationError(
            MediaNormalizationFailureCode.IO_ERROR,
            "A unique normalization temporary file could not be created.",
        )

    @staticmethod
    def _source_file_descriptor(original: BinaryIO) -> int:
        try:
            source_fd = original.fileno()
            source_stat = os.fstat(source_fd)
        except (AttributeError, OSError, ValueError) as error:
            raise MediaNormalizationError(
                MediaNormalizationFailureCode.INVALID_SOURCE,
                "The stored original could not be opened for normalization.",
            ) from error
        if not stat.S_ISREG(source_stat.st_mode) or source_stat.st_size <= 0:
            raise MediaNormalizationError(
                MediaNormalizationFailureCode.INVALID_SOURCE,
                "The stored original is not readable media.",
            )
        return source_fd

    @classmethod
    def _validate_and_sync_output(
        cls,
        *,
        temporary_fd: int,
        directory: DirectoryHandle,
        temporary_name: str,
        expected_stat: os.stat_result,
    ) -> int:
        try:
            descriptor_stat = os.fstat(temporary_fd)
            named_stat = directory.stat(temporary_name, follow_symlinks=False)
            if (
                not stat.S_ISREG(descriptor_stat.st_mode)
                or not os.path.samestat(expected_stat, descriptor_stat)
                or not os.path.samestat(descriptor_stat, named_stat)
            ):
                raise OSError("normalization temporary identity changed")
            cls._validate_wave(temporary_fd)
        except (EOFError, OSError, wave.Error) as error:
            raise cls._corrupted_media_error() from error
        try:
            os.fsync(temporary_fd)
        except OSError as error:
            raise MediaNormalizationError(
                MediaNormalizationFailureCode.IO_ERROR,
                "The normalized audio could not be synchronized.",
            ) from error
        return descriptor_stat.st_size

    @staticmethod
    def _validate_wave(temporary_fd: int) -> None:
        with os.fdopen(os.dup(temporary_fd), "rb") as duplicate:
            duplicate.seek(0)
            with wave.open(duplicate, "rb") as normalized:
                if (
                    normalized.getnchannels() != _CHANNELS
                    or normalized.getframerate() != _SAMPLE_RATE_HZ
                    or normalized.getsampwidth() != _SAMPLE_WIDTH_BYTES
                    or normalized.getcomptype() != "NONE"
                    or normalized.getnframes() <= 0
                ):
                    raise wave.Error("normalization output format is invalid")

    @classmethod
    def _publish_without_replacement(
        cls,
        *,
        directory: DirectoryHandle,
        temporary_name: str,
        destination_name: str,
        expected_stat: os.stat_result,
    ) -> None:
        destination_linked = False
        try:
            current_stat = directory.stat(temporary_name, follow_symlinks=False)
            if not os.path.samestat(expected_stat, current_stat):
                raise OSError("normalization temporary identity changed")
            directory.link(temporary_name, destination_name)
            destination_linked = True
            published_stat = directory.stat(destination_name, follow_symlinks=False)
            if not os.path.samestat(expected_stat, published_stat):
                raise OSError("published normalization identity changed")
            directory.fsync()
        except FileExistsError as error:
            raise MediaNormalizationError(
                MediaNormalizationFailureCode.DESTINATION_EXISTS,
                "A normalized derivative already exists.",
            ) from error
        except OSError as error:
            publication_error = MediaNormalizationError(
                MediaNormalizationFailureCode.IO_ERROR,
                "The normalized derivative could not be published atomically.",
            )
            if destination_linked:
                rollback_error = cls._rollback_publication(
                    directory=directory,
                    destination_name=destination_name,
                )
                if rollback_error is not None:
                    publication_error.add_note(rollback_error)
            raise publication_error from error

    @staticmethod
    def _rollback_publication(
        *,
        directory: DirectoryHandle,
        destination_name: str,
    ) -> str | None:
        try:
            directory.unlink(destination_name)
        except FileNotFoundError:
            pass
        except OSError:
            return "The failed publication rollback could not be confirmed."

        try:
            directory.stat(destination_name, follow_symlinks=False)
        except FileNotFoundError:
            pass
        except OSError:
            return "The failed publication rollback could not be confirmed."
        else:
            return "The failed publication rollback could not be confirmed."

        try:
            directory.fsync()
        except OSError:
            return "The failed publication rollback could not be synchronized."
        return None

    @staticmethod
    def _remove_temporary(directory: DirectoryHandle, temporary_name: str) -> None:
        try:
            directory.unlink(temporary_name)
        except FileNotFoundError:
            return
        except OSError as error:
            raise MediaNormalizationError(
                MediaNormalizationFailureCode.IO_ERROR,
                "Normalization temporary cleanup could not be confirmed.",
            ) from error

    @staticmethod
    def _reject_existing_destination(
        directory: DirectoryHandle,
        destination_name: str,
    ) -> None:
        try:
            directory.stat(destination_name, follow_symlinks=False)
        except FileNotFoundError:
            return
        except OSError as error:
            raise MediaNormalizationError(
                MediaNormalizationFailureCode.IO_ERROR,
                "The normalized derivative destination could not be inspected.",
            ) from error
        raise MediaNormalizationError(
            MediaNormalizationFailureCode.DESTINATION_EXISTS,
            "A normalized derivative already exists.",
        )

    @staticmethod
    def _is_cancelled(
        cancellation: MediaNormalizationCancellationToken | None,
    ) -> bool:
        return cancellation is not None and cancellation.is_cancelled()

    @staticmethod
    def _cancelled_error() -> MediaNormalizationError:
        return MediaNormalizationError(
            MediaNormalizationFailureCode.CANCELLED,
            "Audio normalization was cancelled.",
        )

    @classmethod
    def _exit_error(cls, returncode: int, stderr: str) -> MediaNormalizationError:
        failure = classify_ffmpeg_exit(returncode, stderr)
        if failure is FfmpegFailure.MEDIA:
            return cls._corrupted_media_error()
        if failure is FfmpegFailure.STORAGE:
            return MediaNormalizationError(
                MediaNormalizationFailureCode.IO_ERROR,
                "The normalized audio could not be written.",
            )
        if failure is FfmpegFailure.TOOL:
            return MediaNormalizationError(
                MediaNormalizationFailureCode.TOOL_UNAVAILABLE,
                "The audio normalization tool could not be run.",
            )
        return MediaNormalizationError(
            MediaNormalizationFailureCode.PROCESS_FAILED,
            "Audio normalization failed unexpectedly.",
        )

    @staticmethod
    def _corrupted_media_error() -> MediaNormalizationError:
        return MediaNormalizationError(
            MediaNormalizationFailureCode.CORRUPTED_MEDIA,
            "The selected media is corrupted or could not be decoded completely.",
        )


__all__ = ["FfmpegMediaNormalizer"]
