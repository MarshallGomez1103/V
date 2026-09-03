"""Unit tests for the ffprobe subprocess adapter."""

import json
import subprocess
from pathlib import Path

import pytest

from voz.application.ports.media_probe import (
    MediaProbeError,
    MediaProbeFailureCode,
    MediaStreamKind,
)
from voz.infrastructure.audio.ffprobe import FfprobeMediaProbe

_DECODERS = """\
Decoders:
 V..... = Video
 A..... = Audio
 ------
 V....D h264                 H.264
 A....D aac                  AAC
 A....D pcm_s16le            PCM signed 16-bit little-endian
"""


def _completed(
    command: list[str],
    *,
    stdout: str,
    returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode, stdout, "")


def test_probe_uses_argv_and_validates_detected_codecs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    payload = {
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
            },
        ],
        "format": {"format_name": "mov,mp4,m4a", "duration": "4.125"},
    }

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert "shell" not in kwargs
        if "-decoders" in command:
            return _completed(command, stdout=_DECODERS)
        return _completed(command, stdout=json.dumps(payload))

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = FfprobeMediaProbe(timeout_seconds=2).probe(
        Path("lecture.extension-does-not-matter")
    )

    assert result.format_names == ("mov", "mp4", "m4a")
    assert result.duration_ms == 4_125
    assert result.audio_streams[0].codec_name == "aac"
    assert result.audio_streams[0].sample_rate_hz == 48_000
    assert result.audio_streams[0].channels == 2
    assert all(stream.is_decodable for stream in result.streams)
    assert result.streams[0].kind is MediaStreamKind.VIDEO
    assert calls[0][-1].endswith("lecture.extension-does-not-matter")


def test_probe_rejects_audio_codec_missing_from_installed_decoders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "streams": [
            {
                "index": 0,
                "codec_type": "audio",
                "codec_name": "made_up_codec",
            }
        ],
        "format": {"format_name": "wav"},
    }

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        stdout = _DECODERS if "-decoders" in command else json.dumps(payload)
        return _completed(command, stdout=stdout)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(MediaProbeError) as captured:
        FfprobeMediaProbe().probe(Path("looks-valid.wav"))

    assert captured.value.code is MediaProbeFailureCode.NO_DECODABLE_AUDIO
    assert "looks-valid.wav" not in captured.value.user_message


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (FileNotFoundError(), MediaProbeFailureCode.TOOL_UNAVAILABLE),
        (
            subprocess.TimeoutExpired(["ffprobe"], 0.01),
            MediaProbeFailureCode.TIMED_OUT,
        ),
    ],
)
def test_probe_maps_subprocess_failures_without_exposing_the_path(
    monkeypatch: pytest.MonkeyPatch,
    failure: OSError | subprocess.TimeoutExpired,
    expected_code: MediaProbeFailureCode,
) -> None:
    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del command, kwargs
        raise failure

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(MediaProbeError) as captured:
        FfprobeMediaProbe().probe(Path("/secret/classes/private.wav"))

    assert captured.value.code is expected_code
    assert "/secret" not in str(captured.value)


def test_probe_rejects_malformed_json_as_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        return _completed(command, stdout="{")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(MediaProbeError) as captured:
        FfprobeMediaProbe().probe(Path("broken.wav"))

    assert captured.value.code is MediaProbeFailureCode.INVALID_RESPONSE
