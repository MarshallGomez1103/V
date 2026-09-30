"""Real FFmpeg decoding, derivative preference and on-disk cache."""

from __future__ import annotations

import json
import shutil
import wave
from pathlib import Path
from uuid import uuid4

import pytest

from voz.application.ports.waveform import WaveformError, WaveformFailureCode
from voz.infrastructure.audio.waveform_peaks import FfmpegWaveformPeaks
from voz.infrastructure.media_storage import FileSystemMediaStorage

FIXTURES = Path(__file__).parents[2] / "fixtures/media"
SHA = "b" * 64

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg is required"
)


class _Env:
    def __init__(self, tmp_path: Path) -> None:
        self.data = tmp_path / "data"
        self.cache = tmp_path / "cache-root"
        self.storage = FileSystemMediaStorage(self.data)
        self.project_id = uuid4()
        self.media_id = uuid4()

    def import_fixture(self, name: str) -> None:
        self.storage.import_original(
            source=FIXTURES / name,
            project_id=self.project_id,
            media_asset_id=self.media_id,
        )

    def adapter(self, executable: str = "ffmpeg") -> FfmpegWaveformPeaks:
        return FfmpegWaveformPeaks(
            storage_root=self.data,
            cache_root=self.cache,
            media_storage=self.storage,
            executable=executable,
        )

    def peaks(self, adapter: FfmpegWaveformPeaks, buckets: int = 100):
        return adapter.peaks(
            project_id=self.project_id,
            media_asset_id=self.media_id,
            content_sha256=SHA,
            buckets=buckets,
        )


@pytest.fixture
def env(tmp_path: Path) -> _Env:
    return _Env(tmp_path)


@pytest.mark.parametrize(
    "name",
    [path.name for path in sorted(FIXTURES.glob("synthetic-tone.*"))],
)
def test_real_fixtures_produce_normalized_peaks(env: _Env, name: str) -> None:
    env.import_fixture(name)

    series = env.peaks(env.adapter(), 200)

    assert len(series.peaks) == 200
    assert 200 <= series.duration_ms <= 400
    flat = [value for pair in series.peaks for value in pair]
    assert all(-1.0 <= value <= 1.0 for value in flat)
    assert max(abs(value) for value in flat) == 1.0
    assert all(low <= high for low, high in series.peaks)
    assert all(round(value, 3) == value for value in flat)


def test_normalized_derivative_is_preferred_over_the_original(env: _Env) -> None:
    env.import_fixture("synthetic-tone.wav")
    derivatives = env.data / "projects" / str(env.project_id) / "derivatives"
    derivatives.mkdir(parents=True)
    with wave.open(str(derivatives / f"{env.media_id}.inference.wav"), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16_000)
        out.writeframes(b"\x00\x00" * 16_000)  # 1 s of silence

    series = env.peaks(env.adapter())

    # The original is a 0.25 s tone; the derivative is 1 s of silence.
    assert series.duration_ms == 1000
    assert set(series.peaks) == {(0.0, 0.0)}


def test_second_request_is_served_from_cache_without_decoding(env: _Env) -> None:
    env.import_fixture("synthetic-tone.wav")
    first = env.peaks(env.adapter())

    cached = env.peaks(env.adapter(executable="/nonexistent/ffmpeg"))

    assert cached == first
    files = list((env.cache / "waveforms").iterdir())
    assert [file.name for file in files] == [f"v1-{SHA}-100.json"]


def test_cache_is_keyed_by_bucket_count(env: _Env) -> None:
    env.import_fixture("synthetic-tone.wav")
    env.peaks(env.adapter(), 100)
    env.peaks(env.adapter(), 150)

    names = sorted(file.name for file in (env.cache / "waveforms").iterdir())
    assert names == [f"v1-{SHA}-100.json", f"v1-{SHA}-150.json"]


def test_corrupt_cache_is_ignored_and_rewritten(env: _Env) -> None:
    env.import_fixture("synthetic-tone.wav")
    cache_file = env.cache / "waveforms" / f"v1-{SHA}-100.json"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text("{not json", encoding="utf-8")

    series = env.peaks(env.adapter())

    assert len(series.peaks) == 100
    assert json.loads(cache_file.read_text())["duration_ms"] == series.duration_ms


def test_missing_media_is_unavailable_without_paths(env: _Env) -> None:
    with pytest.raises(WaveformError) as caught:
        env.peaks(env.adapter())

    assert caught.value.code is WaveformFailureCode.UNAVAILABLE
    assert str(env.data) not in caught.value.user_message


def test_missing_ffmpeg_is_unavailable(env: _Env) -> None:
    env.import_fixture("synthetic-tone.wav")

    with pytest.raises(WaveformError) as caught:
        env.peaks(env.adapter(executable="/nonexistent/ffmpeg"))

    assert caught.value.code is WaveformFailureCode.UNAVAILABLE
    assert not (env.cache / "waveforms").exists()


def test_undecodable_media_is_unavailable_and_not_cached(
    env: _Env, tmp_path: Path
) -> None:
    junk = tmp_path / "junk.bin"
    junk.write_bytes(b"this is not audio" * 100)
    env.storage.import_original(
        source=junk, project_id=env.project_id, media_asset_id=env.media_id
    )

    with pytest.raises(WaveformError) as caught:
        env.peaks(env.adapter())

    assert caught.value.code is WaveformFailureCode.UNAVAILABLE
    assert not list((env.cache / "waveforms").glob("*.json"))
