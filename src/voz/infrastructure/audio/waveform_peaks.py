"""FFmpeg-backed waveform peaks with bounded memory and an on-disk cache."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from array import array
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

from voz.application.ports.inference_audio import InferenceAudioError
from voz.application.ports.media_storage import MediaStorageError
from voz.application.ports.waveform import (
    PeakSeries,
    WaveformError,
    WaveformFailureCode,
)
from voz.infrastructure.inference_audio import FileSystemInferenceAudioSource
from voz.infrastructure.media_storage import FileSystemMediaStorage

SAMPLE_RATE_HZ = 8_000
_READ_BYTES = 64 * 1024
_INITIAL_BLOCK_SAMPLES = 64
_CACHE_VERSION = "v1"
_MAX_CACHE_BYTES = 4 * 1024 * 1024
_SAMPLE_PEAK = 32768.0


class PeakAccumulator:
    """Stream PCM samples into at most ``2 * buckets`` (min, max) blocks.

    Blocks start small and double (pairwise merge) whenever the cap is exceeded,
    so memory is ``O(buckets)`` for any duration. ``finish`` resamples the
    blocks to exactly ``buckets`` pairs. The trailing unfinished block is kept
    open, so time stays uniform to within one block.
    """

    def __init__(self, buckets: int) -> None:
        if type(buckets) is not int or buckets <= 0:
            raise ValueError("buckets must be a positive integer")
        self._buckets = buckets
        self._cap = buckets * 2
        self._block = _INITIAL_BLOCK_SAMPLES
        self._mins: list[int] = []
        self._maxs: list[int] = []
        self._open_min = 0
        self._open_max = 0
        self._open_count = 0
        self.total_samples = 0

    @property
    def block_count(self) -> int:
        """Closed blocks held in memory (never above ``2 * buckets``)."""
        return len(self._mins)

    def feed(self, samples: Sequence[int]) -> None:
        """Consume signed 16-bit samples (any chunking gives identical results)."""
        self.total_samples += len(samples)
        position = 0
        while position < len(samples):
            take = min(self._block - self._open_count, len(samples) - position)
            chunk = samples[position : position + take]
            low, high = min(chunk), max(chunk)
            if self._open_count == 0:
                self._open_min, self._open_max = low, high
            else:
                self._open_min = min(self._open_min, low)
                self._open_max = max(self._open_max, high)
            self._open_count += take
            position += take
            if self._open_count == self._block:
                self._close_open()

    def _close_open(self) -> None:
        self._mins.append(self._open_min)
        self._maxs.append(self._open_max)
        self._open_count = 0
        if len(self._mins) > self._cap:
            self._halve()

    def _halve(self) -> None:
        leftover = len(self._mins) % 2
        if leftover:
            # The odd last block becomes the (partial) open block of the new size.
            self._open_min, self._open_max = self._mins.pop(), self._maxs.pop()
            self._open_count = self._block
        self._mins = [min(a, b) for a, b in zip(*[iter(self._mins)] * 2, strict=True)]
        self._maxs = [max(a, b) for a, b in zip(*[iter(self._maxs)] * 2, strict=True)]
        self._block *= 2

    def finish(self) -> list[tuple[int, int]]:
        """Return exactly ``buckets`` raw ``(min, max)`` pairs (empty if no audio)."""
        mins, maxs = list(self._mins), list(self._maxs)
        if self._open_count:
            mins.append(self._open_min)
            maxs.append(self._open_max)
        blocks = len(mins)
        if blocks == 0:
            return []
        result: list[tuple[int, int]] = []
        for index in range(self._buckets):
            start = index * blocks // self._buckets
            end = max(start + 1, (index + 1) * blocks // self._buckets)
            result.append((min(mins[start:end]), max(maxs[start:end])))
        return result


def normalize_peaks(raw: Sequence[tuple[int, int]]) -> tuple[tuple[float, float], ...]:
    """Scale so the loudest sample maps to +/-1, rounded to 3 decimals."""
    loudest = max((max(abs(low), abs(high)) for low, high in raw), default=0)
    if loudest == 0:
        return tuple((0.0, 0.0) for _ in raw)
    scale = 1.0 / loudest
    return tuple((round(low * scale, 3), round(high * scale, 3)) for low, high in raw)


def duration_ms_from_samples(total_samples: int) -> int:
    """Duration of mono ``SAMPLE_RATE_HZ`` audio in whole milliseconds."""
    return total_samples * 1000 // SAMPLE_RATE_HZ


class FfmpegWaveformPeaks:
    """Decode to 8 kHz mono s16le through a pipe and cache the peaks on disk."""

    def __init__(
        self,
        *,
        storage_root: Path,
        cache_root: Path,
        media_storage: FileSystemMediaStorage,
        executable: str = "ffmpeg",
        timeout_seconds: float = 600.0,
    ) -> None:
        if not executable.strip():
            raise ValueError("executable must not be blank")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._storage_root = Path(storage_root).absolute()
        self._cache_dir = Path(cache_root).absolute() / "waveforms"
        self._media_storage = media_storage
        self._executable = executable
        self._timeout_seconds = timeout_seconds

    def peaks(
        self,
        *,
        project_id: UUID,
        media_asset_id: UUID,
        content_sha256: str,
        buckets: int,
    ) -> PeakSeries:
        cache_file = (
            self._cache_dir / f"{_CACHE_VERSION}-{content_sha256}-{buckets}.json"
        )
        cached = self._read_cache(cache_file, buckets)
        if cached is not None:
            return cached
        with self._open_source(project_id, media_asset_id) as source:
            series = self._decode(source, buckets)
        self._write_cache(cache_file, series)
        return series

    def _open_source(self, project_id: UUID, media_asset_id: UUID) -> BinaryIO:
        """Prefer the normalized derivative; fall back to the original."""
        try:
            return FileSystemInferenceAudioSource(
                self._storage_root, project_id, media_asset_id
            ).open()
        except InferenceAudioError:
            pass
        try:
            return self._media_storage.open_original(
                project_id=project_id, media_asset_id=media_asset_id
            )
        except MediaStorageError as error:
            raise _unavailable("The media file is not available.") from error

    def _decode(self, source: BinaryIO, buckets: int) -> PeakSeries:
        command = [
            self._executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-i",
            f"/proc/self/fd/{source.fileno()}",
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE_HZ),
            "-f",
            "s16le",
            "pipe:1",
        ]
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                pass_fds=(source.fileno(),),
            )
        except OSError as error:
            raise _unavailable("The audio decoder could not be started.") from error

        accumulator = PeakAccumulator(buckets)
        watchdog = threading.Timer(self._timeout_seconds, process.kill)
        watchdog.daemon = True
        watchdog.start()
        try:
            assert process.stdout is not None
            carry = b""
            while chunk := process.stdout.read(_READ_BYTES):
                data = carry + chunk
                usable = len(data) - len(data) % 2
                carry = data[usable:]
                samples = array("h")
                samples.frombytes(data[:usable])
                if sys.byteorder == "big":
                    samples.byteswap()
                accumulator.feed(samples)
            returncode = process.wait()
        except BaseException:
            process.kill()
            raise
        finally:
            watchdog.cancel()
            if process.poll() is None:
                process.kill()
            with suppress(OSError, ValueError):
                if process.stdout is not None:
                    process.stdout.close()
            with suppress(subprocess.TimeoutExpired):
                process.wait(timeout=5)

        raw = accumulator.finish()
        if returncode != 0 or not raw:
            raise _unavailable("The audio could not be decoded for the waveform.")
        return PeakSeries(
            duration_ms=duration_ms_from_samples(accumulator.total_samples),
            peaks=normalize_peaks(raw),
        )

    @staticmethod
    def _read_cache(cache_file: Path, buckets: int) -> PeakSeries | None:
        try:
            if cache_file.stat().st_size > _MAX_CACHE_BYTES:
                return None
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            duration_ms = payload["duration_ms"]
            peaks = tuple((float(low), float(high)) for low, high in payload["peaks"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if type(duration_ms) is not int or len(peaks) != buckets:
            return None
        if any(not -1.0 <= value <= 1.0 for pair in peaks for value in pair):
            return None
        return PeakSeries(duration_ms=duration_ms, peaks=peaks)

    def _write_cache(self, cache_file: Path, series: PeakSeries) -> None:
        temporary = cache_file.with_name(f".{uuid4()}.tmp")
        payload = {"duration_ms": series.duration_ms, "peaks": series.peaks}
        # ponytail: the cache is best-effort; a failed write only costs a re-decode.
        try:
            self._cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8") as output:
                json.dump(payload, output)
                output.flush()
                os.fsync(output.fileno())  # data on disk before the rename
            os.replace(temporary, cache_file)
        except OSError:
            with suppress(OSError):
                temporary.unlink()


def _unavailable(message: str) -> WaveformError:
    return WaveformError(WaveformFailureCode.UNAVAILABLE, message)


__all__ = [
    "SAMPLE_RATE_HZ",
    "FfmpegWaveformPeaks",
    "PeakAccumulator",
    "duration_ms_from_samples",
    "normalize_peaks",
]
