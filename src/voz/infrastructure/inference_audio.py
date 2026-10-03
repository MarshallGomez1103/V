"""Safe filesystem access to normalized inference audio."""

from __future__ import annotations

import os
import stat
import wave
from contextlib import suppress
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, cast
from uuid import UUID

from voz.application.ports.inference_audio import (
    InferenceAudioError,
    InferenceAudioFailureCode,
)
from voz.application.ports.transcription import TranscriptionClip
from voz.infrastructure.safe_fs import open_directory_chain


class FileSystemInferenceAudioSource:
    """Open one UUID-addressed derivative without exposing its host path."""

    def __init__(
        self,
        storage_root: Path,
        project_id: UUID,
        media_asset_id: UUID,
    ) -> None:
        raw_project_id = cast(object, project_id)
        if not isinstance(raw_project_id, UUID):
            raise TypeError("project_id must be a UUID")
        raw_media_asset_id = cast(object, media_asset_id)
        if not isinstance(raw_media_asset_id, UUID):
            raise TypeError("media_asset_id must be a UUID")
        self._storage_root = Path(storage_root).absolute()
        self._project_id = project_id
        self._media_asset_id = media_asset_id

    def open(self, clip: TranscriptionClip | None = None) -> BinaryIO:
        """Return the whole WAV or a bounded in-memory PCM WAV clip."""
        audio = self._open_full()
        if clip is None:
            return audio
        try:
            return self._read_clip(audio, clip)
        finally:
            audio.close()

    def _open_full(self) -> BinaryIO:
        try:
            directory = open_directory_chain(
                self._storage_root,
                ("projects", str(self._project_id), "derivatives"),
                create=False,
            )
        except FileNotFoundError as error:
            raise self._not_found() from error
        except OSError as error:
            raise self._unsafe_path() from error
        audio_fd: int | None = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            try:
                audio_fd = directory.open_file(
                    f"{self._media_asset_id}.inference.wav", flags
                )
            except FileNotFoundError as error:
                raise self._not_found() from error
            except OSError as error:
                raise self._unsafe_path() from error

            try:
                audio_stat = os.fstat(audio_fd)
            except OSError as error:
                raise InferenceAudioError(
                    InferenceAudioFailureCode.IO_ERROR,
                    "The normalized audio could not be inspected.",
                ) from error
            if not stat.S_ISREG(audio_stat.st_mode):
                raise self._unsafe_path()
            try:
                audio = os.fdopen(audio_fd, "rb", closefd=True)
            except (OSError, ValueError) as error:
                raise InferenceAudioError(
                    InferenceAudioFailureCode.IO_ERROR,
                    "The normalized audio could not be opened for reading.",
                ) from error
            audio_fd = None
            return audio
        finally:
            if audio_fd is not None:
                with suppress(OSError):
                    os.close(audio_fd)
            with suppress(OSError):
                directory.close()

    @staticmethod
    def _read_clip(audio: BinaryIO, clip: TranscriptionClip) -> BytesIO:
        try:
            with wave.open(audio, "rb") as source:
                if source.getcomptype() != "NONE":
                    raise wave.Error("normalized audio must be PCM")
                frame_rate = source.getframerate()
                frame_count = source.getnframes()
                start_frame = clip.start_ms * frame_rate // 1_000
                end_frame = min(
                    frame_count,
                    (clip.end_ms * frame_rate + 999) // 1_000,
                )
                if start_frame >= frame_count or end_frame <= start_frame:
                    raise wave.Error("clip lies outside normalized audio")
                source.setpos(start_frame)
                frames = source.readframes(end_frame - start_frame)
                channels = source.getnchannels()
                sample_width = source.getsampwidth()
        except (EOFError, OSError, wave.Error) as error:
            raise InferenceAudioError(
                InferenceAudioFailureCode.INVALID_AUDIO,
                "The normalized audio is invalid or cannot provide this clip.",
            ) from error

        output = BytesIO()
        with wave.open(output, "wb") as destination:
            destination.setnchannels(channels)
            destination.setsampwidth(sample_width)
            destination.setframerate(frame_rate)
            destination.writeframes(frames)
        output.seek(0)
        return output

    @staticmethod
    def _not_found() -> InferenceAudioError:
        return InferenceAudioError(
            InferenceAudioFailureCode.NOT_FOUND,
            "The normalized audio is not available.",
        )

    @staticmethod
    def _unsafe_path() -> InferenceAudioError:
        return InferenceAudioError(
            InferenceAudioFailureCode.UNSAFE_STORAGE_PATH,
            "The normalized audio could not be opened safely.",
        )


__all__ = ["FileSystemInferenceAudioSource"]
