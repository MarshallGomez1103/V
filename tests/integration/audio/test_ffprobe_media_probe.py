"""Integration tests against the locally installed ffprobe executable."""

import wave
from pathlib import Path

import pytest

from voz.application.ports.media_probe import (
    MediaProbeError,
    MediaProbeFailureCode,
    MediaStreamKind,
)
from voz.infrastructure.audio.ffprobe import FfprobeMediaProbe


def _write_silent_pcm_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        output.writeframes(b"\x00\x00" * 1_600)


def test_real_ffprobe_accepts_media_content_with_unrelated_extension(
    tmp_path: Path,
) -> None:
    source = tmp_path / "class.notes"
    _write_silent_pcm_wav(source)

    result = FfprobeMediaProbe().probe(source)

    assert "wav" in result.format_names
    assert result.duration_ms == 100
    assert result.audio_streams == (result.streams[0],)
    assert result.streams[0].kind is MediaStreamKind.AUDIO
    assert result.streams[0].codec_name == "pcm_s16le"
    assert result.streams[0].sample_rate_hz == 16_000
    assert result.streams[0].channels == 1
    assert result.streams[0].is_decodable


def test_real_ffprobe_rejects_corrupt_file_despite_audio_extension(
    tmp_path: Path,
) -> None:
    source = tmp_path / "not-really-audio.wav"
    source.write_bytes(b"this is not media")

    with pytest.raises(MediaProbeError) as captured:
        FfprobeMediaProbe().probe(source)

    assert captured.value.code is MediaProbeFailureCode.INVALID_MEDIA
    assert source.name not in captured.value.user_message
