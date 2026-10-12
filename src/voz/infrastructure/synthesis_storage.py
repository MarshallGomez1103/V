"""Filesystem adapter for the immutable WAV produced by synthesis jobs (ADR-0010).

Layout: ``<data_root>/synthesis/<job_id>/audio.wav`` (PCM16 mono at the model's
sample rate). The WAV is built in a temporary file next to its destination,
hashed, flushed and made read-only, then published with a non-replacing hard
link, exactly like originals in :mod:`voz.infrastructure.media_storage`.
"""

from __future__ import annotations

import hashlib
import os
import stat
import sys
import wave
from array import array
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

from voz.application.ports.speech_synthesis import PcmAudio, PcmSampleFormat
from voz.application.ports.synthesis_audio_storage import (
    SynthesisStorageError,
    SynthesisStorageErrorCode,
)
from voz.domain.entities.synthesized_audio import SynthesizedAudio
from voz.infrastructure._payload import require_uuid
from voz.infrastructure.safe_fs import (
    DirectoryDurabilityError,
    DirectoryHandle,
    fchmod,
    open_directory_chain,
    remove_directory_tree,
)

_ROOT_DIR = "synthesis"
_AUDIO_NAME = "audio.wav"
_READ_ONLY_MODE = 0o444
_HASH_CHUNK_BYTES = 1024 * 1024
_BIG_ENDIAN = sys.byteorder == "big"
_Code = SynthesisStorageErrorCode


def _error(code: SynthesisStorageErrorCode, message: str) -> SynthesisStorageError:
    return SynthesisStorageError(code, message)


def _int16_bytes(chunk: PcmAudio) -> bytes:
    """Chunk as native-endian int16 bytes (what ``wave`` expects)."""
    if chunk.sample_format is PcmSampleFormat.INT16:
        if not _BIG_ENDIAN:
            return chunk.samples
        pcm = array("h", chunk.samples)
        pcm.byteswap()  # engines deliver little-endian
        return pcm.tobytes()
    floats = array("f", chunk.samples)
    if _BIG_ENDIAN:
        floats.byteswap()
    # NaN becomes silence; everything else saturates to the int16 range.
    pcm = array(
        "h",
        (
            0
            if value != value
            else max(-32768, min(32767, round(max(-1.0, min(1.0, value)) * 32768)))
            for value in floats
        ),
    )
    return pcm.tobytes()


class FileSystemSynthesisStorage:
    """Store synthesis WAVs below a trusted runtime-data root."""

    def __init__(self, data_root: Path) -> None:
        self._data_root = Path(data_root).absolute()

    def write(
        self,
        job_id: UUID,
        chunks: Sequence[PcmAudio],
        gaps_ms: Sequence[int],
    ) -> SynthesizedAudio:
        """Join chunks and silences into one immutable WAV."""
        require_uuid(job_id, field="job_id")
        if not chunks:
            raise _error(_Code.NO_AUDIO, "There is no audio to store.")
        if len(gaps_ms) != len(chunks) - 1 or any(
            type(gap) is not int or gap < 0 for gap in gaps_ms
        ):
            raise ValueError("gaps_ms needs one non-negative int per chunk boundary")
        sample_rate = chunks[0].sample_rate
        if any(chunk.sample_rate != sample_rate for chunk in chunks):
            raise _error(
                _Code.SAMPLE_RATE_MISMATCH,
                "All chunks of one audio must share the same sample rate.",
            )

        relative_path = f"{_ROOT_DIR}/{job_id}/{_AUDIO_NAME}"
        directory: DirectoryHandle | None = None
        temporary_name: str | None = None
        published = False
        try:
            directory = self._open_job_directory(job_id, create=True)
            temporary_name, temporary_fd = self._create_temporary(directory)
            frames, digest, size = self._build_wav(
                temporary_fd, sample_rate, chunks, gaps_ms
            )
            self._publish_without_replacement(directory, temporary_name)
            published = True
            return SynthesizedAudio(
                job_id=job_id,
                relative_path=relative_path,
                duration_ms=max(1, round(frames * 1000 / sample_rate)),
                sample_rate=sample_rate,
                chunk_count=len(chunks),
                sha256=digest,
                size_bytes=size,
            )
        except SynthesisStorageError:
            raise
        except OSError as error:
            raise _error(
                _Code.IO_ERROR,
                "The audio could not be stored due to a filesystem error.",
            ) from error
        finally:
            if directory is not None:
                with suppress(OSError):
                    if temporary_name is not None:
                        self._remove_temporary(directory, temporary_name)
                    if published and not hasattr(os, "fchmod"):
                        # Windows < 3.13: the read-only attribute is shared by
                        # every hard link, so it goes on the final name last.
                        # ponytail: writable for those few microseconds.
                        directory.chmod(_AUDIO_NAME, _READ_ONLY_MODE)
                    if not published:
                        # Drop the job directory only if it is still empty.
                        parent = open_directory_chain(
                            self._data_root, (_ROOT_DIR,), create=False
                        )
                        try:
                            parent.rmdir(str(job_id))
                        finally:
                            parent.close()
                with suppress(OSError):
                    directory.close()

    def open_for_reading(self, relative_path: str) -> BinaryIO:
        """Open a stored WAV without returning its host path to callers."""
        job_id = self._parse_relative_path(relative_path)
        directory = self._open_job_directory(job_id, create=False)
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        try:
            try:
                descriptor = directory.open_file(_AUDIO_NAME, flags)
            except FileNotFoundError as error:
                raise _error(
                    _Code.AUDIO_NOT_FOUND, "The requested audio is not available."
                ) from error
            except OSError as error:
                raise _error(
                    _Code.UNSAFE_STORAGE_PATH,
                    "The stored audio could not be opened safely.",
                ) from error
            try:
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise _error(
                        _Code.UNSAFE_STORAGE_PATH,
                        "The stored audio is not a regular file.",
                    )
                return os.fdopen(descriptor, "rb", closefd=True)
            except BaseException:
                with suppress(OSError):
                    os.close(descriptor)
                raise
        finally:
            directory.close()

    def delete(self, relative_path: str) -> None:
        """Remove the job directory; links inside it are unlinked, never followed."""
        self.delete_job(self._parse_relative_path(relative_path))

    def delete_job(self, job_id: UUID) -> None:
        """Remove the job directory (leftovers included); a no-op when absent."""
        require_uuid(job_id, field="job_id")
        try:
            remove_directory_tree(self._data_root, (_ROOT_DIR, str(job_id)))
        except OSError as error:
            raise _error(
                _Code.UNSAFE_STORAGE_PATH, "The audio could not be deleted safely."
            ) from error

    @staticmethod
    def _parse_relative_path(relative_path: str) -> UUID:
        """Accept exactly ``synthesis/<canonical uuid>/audio.wav``."""
        parts = relative_path.split("/")
        if len(parts) == 3 and parts[0] == _ROOT_DIR and parts[2] == _AUDIO_NAME:
            with suppress(ValueError):
                job_id = UUID(parts[1])
                if str(job_id) == parts[1]:
                    return job_id
        raise _error(_Code.INVALID_PATH, "The audio path is not valid.")

    def _open_job_directory(self, job_id: UUID, *, create: bool) -> DirectoryHandle:
        try:
            return open_directory_chain(
                self._data_root,
                (_ROOT_DIR, str(job_id)),
                create=create,
                durable=True,
            )
        except DirectoryDurabilityError as error:
            raise _error(
                _Code.IO_ERROR, "The audio directory could not be created durably."
            ) from error
        except FileNotFoundError as error:
            if create:
                raise _error(
                    _Code.UNSAFE_STORAGE_PATH, "The audio storage path is unsafe."
                ) from error
            raise _error(
                _Code.AUDIO_NOT_FOUND, "The requested audio is not available."
            ) from error
        except OSError as error:
            raise _error(
                _Code.UNSAFE_STORAGE_PATH, "The audio storage path is unsafe."
            ) from error

    @staticmethod
    def _create_temporary(directory: DirectoryHandle) -> tuple[str, int]:
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        for _ in range(10):
            name = f".audio-{uuid4()}.tmp"
            try:
                return name, directory.open_file(name, flags, 0o600)
            except FileExistsError:
                continue
        raise _error(_Code.IO_ERROR, "A unique temporary audio could not be created.")

    @staticmethod
    def _build_wav(
        descriptor: int,
        sample_rate: int,
        chunks: Sequence[PcmAudio],
        gaps_ms: Sequence[int],
    ) -> tuple[int, str, int]:
        """Write, hash, seal and flush the temporary WAV; returns frames, sha, size."""
        try:
            output = os.fdopen(descriptor, "w+b", closefd=True)
        except (OSError, ValueError):
            with suppress(OSError):
                os.close(descriptor)
            raise
        with output:
            frames = 0
            with wave.open(output, "wb") as writer:
                writer.setnchannels(1)
                writer.setsampwidth(2)
                writer.setframerate(sample_rate)
                # ponytail: 4 GiB RIFF ceiling; ~6 h at 24 kHz, far above a job.
                for index, chunk in enumerate(chunks):
                    writer.writeframes(_int16_bytes(chunk))
                    frames += chunk.frame_count
                    if index < len(gaps_ms):
                        silence = round(gaps_ms[index] * sample_rate / 1000)
                        writer.writeframes(bytes(silence * 2))
                        frames += silence
            output.flush()
            output.seek(0)
            digest = hashlib.sha256()
            while block := output.read(_HASH_CHUNK_BYTES):
                digest.update(block)
            fchmod(output.fileno(), _READ_ONLY_MODE)
            os.fsync(output.fileno())
            return frames, digest.hexdigest(), os.fstat(output.fileno()).st_size

    @staticmethod
    def _publish_without_replacement(
        directory: DirectoryHandle, temporary_name: str
    ) -> None:
        try:
            directory.link(temporary_name, _AUDIO_NAME)
        except FileExistsError as error:
            raise _error(
                _Code.AUDIO_EXISTS, "An audio already exists for this job."
            ) from error
        except OSError as error:
            raise _error(
                _Code.IO_ERROR, "The audio could not be published atomically."
            ) from error
        try:
            directory.fsync()
        except OSError as error:
            with suppress(OSError):
                directory.unlink(_AUDIO_NAME)
                directory.fsync()
            raise _error(
                _Code.IO_ERROR, "The audio publication failed and was rolled back."
            ) from error

    @staticmethod
    def _remove_temporary(directory: DirectoryHandle, temporary_name: str) -> None:
        try:
            directory.unlink(temporary_name)
        except FileNotFoundError:
            return
        directory.fsync()


__all__ = ["FileSystemSynthesisStorage"]
