"""A decoder that never finishes is cut off by the watchdog."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

from voz.application.ports.waveform import WaveformError, WaveformFailureCode
from voz.infrastructure.audio.waveform_peaks import FfmpegWaveformPeaks
from voz.infrastructure.media_storage import FileSystemMediaStorage

FIXTURE = Path(__file__).parents[3] / "fixtures/media/synthetic-tone.wav"


@pytest.mark.skipif(os.name == "nt", reason="needs a POSIX shell script")
def test_hung_decoder_is_killed_and_reported_without_paths(tmp_path: Path) -> None:
    fake = tmp_path / "tools" / "ffmpeg"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\nexec sleep 60\n", encoding="utf-8")
    fake.chmod(0o755)
    storage = FileSystemMediaStorage(tmp_path / "data")
    project_id, media_id = uuid4(), uuid4()
    storage.import_original(
        source=FIXTURE, project_id=project_id, media_asset_id=media_id
    )
    adapter = FfmpegWaveformPeaks(
        storage_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        media_storage=storage,
        executable=str(fake),
        timeout_seconds=0.3,
    )

    with pytest.raises(WaveformError) as captured:
        adapter.peaks(
            project_id=project_id,
            media_asset_id=media_id,
            content_sha256="c" * 64,
            buckets=50,
        )

    assert captured.value.code is WaveformFailureCode.UNAVAILABLE
    assert str(tmp_path) not in str(captured.value)
