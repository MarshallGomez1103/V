"""Storage, probe, normalize and waveform on every platform strategy.

``platform_mode`` (tests/conftest.py) runs each test natively and with the
Windows/macOS fallbacks forced, so those branches are verified on Linux.
"""

from __future__ import annotations

import hashlib
import shutil
import stat
import wave
from pathlib import Path
from uuid import uuid4

import pytest

from voz.application.ports.media_storage import (
    MediaStorageError,
    MediaStorageErrorCode,
)
from voz.infrastructure.audio.ffmpeg import FfmpegMediaNormalizer
from voz.infrastructure.audio.ffprobe import FfprobeMediaProbe
from voz.infrastructure.audio.waveform_peaks import FfmpegWaveformPeaks
from voz.infrastructure.inference_audio import FileSystemInferenceAudioSource
from voz.infrastructure.media_storage import FileSystemMediaStorage

MEDIA_FIXTURE = Path(__file__).parents[2] / "fixtures/media/synthetic-tone.webm"

pytestmark = [
    pytest.mark.windows_ok,
    pytest.mark.skipif(
        shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
        reason="ffmpeg and ffprobe are required",
    ),
]


def test_import_open_discard_and_immutability(
    tmp_path: Path, platform_mode: str
) -> None:
    storage = FileSystemMediaStorage(tmp_path / "data")
    project_id, media_id = uuid4(), uuid4()
    digest = hashlib.sha256(MEDIA_FIXTURE.read_bytes()).hexdigest()

    imported = storage.import_original(
        source=MEDIA_FIXTURE, project_id=project_id, media_asset_id=media_id
    )

    assert imported.media_asset.content_sha256 == digest
    stored = storage.original_path_for(project_id, media_id)
    assert not stored.stat().st_mode & stat.S_IWUSR  # read-only original
    assert not list(stored.parent.glob(".import-*"))
    with storage.open_original(project_id=project_id, media_asset_id=media_id) as f:
        assert hashlib.sha256(f.read()).hexdigest() == digest
    with pytest.raises(MediaStorageError) as exists:
        storage.import_original(
            source=MEDIA_FIXTURE, project_id=project_id, media_asset_id=media_id
        )
    assert exists.value.code is MediaStorageErrorCode.DESTINATION_EXISTS

    storage.discard_original(project_id=project_id, media_asset_id=media_id)
    assert not stored.exists()
    storage.discard_original(project_id=project_id, media_asset_id=media_id)


def test_probe_normalize_and_waveform_end_to_end(
    tmp_path: Path, platform_mode: str
) -> None:
    data = tmp_path / "data"
    storage = FileSystemMediaStorage(data)
    project_id, media_id = uuid4(), uuid4()
    storage.import_original(
        source=MEDIA_FIXTURE, project_id=project_id, media_asset_id=media_id
    )
    with storage.open_original(project_id=project_id, media_asset_id=media_id) as f:
        probe = FfprobeMediaProbe().probe(f)
    assert probe.duration_ms is not None
    assert probe.audio_streams

    normalizer = FfmpegMediaNormalizer(data)
    with storage.open_original(project_id=project_id, media_asset_id=media_id) as f:
        result = normalizer.normalize(
            original=f,
            project_id=project_id,
            media_asset_id=media_id,
            duration_ms=probe.duration_ms,
            audio_stream_index=probe.audio_streams[0].index,
        )
    destination = normalizer.normalized_path_for(project_id, media_id)
    assert result.bytes_written == destination.stat().st_size
    assert not list(destination.parent.glob(".normalize-*"))
    with wave.open(str(destination), "rb") as wav:
        assert (wav.getframerate(), wav.getnchannels()) == (16_000, 1)

    with FileSystemInferenceAudioSource(data, project_id, media_id).open() as audio:
        assert audio.read(4) == b"RIFF"

    peaks = FfmpegWaveformPeaks(
        storage_root=data, cache_root=tmp_path / "cache", media_storage=storage
    ).peaks(
        project_id=project_id,
        media_asset_id=media_id,
        content_sha256="c" * 64,
        buckets=50,
    )
    assert len(peaks.peaks) == 50
    assert peaks.duration_ms > 0
