"""Unit tests for the ffprobe subprocess adapter."""

import json
import subprocess
from io import BytesIO
from tempfile import TemporaryFile

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
 A....D dca                  DCA (DTS Coherent Acoustics) (codec dts)
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
    call_kwargs: list[dict[str, object]] = []
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
        call_kwargs.append(kwargs)
        assert "shell" not in kwargs
        if "-decoders" in command:
            return _completed(command, stdout=_DECODERS)
        return _completed(command, stdout=json.dumps(payload))

    monkeypatch.setattr(subprocess, "run", fake_run)

    with TemporaryFile("w+b") as source:
        source_fd = source.fileno()
        result = FfprobeMediaProbe(timeout_seconds=2).probe(source)

    assert result.format_names == ("mov", "mp4", "m4a")
    assert result.duration_ms == 4_125
    assert result.audio_streams[0].codec_name == "aac"
    assert result.audio_streams[0].sample_rate_hz == 48_000
    assert result.audio_streams[0].channels == 2
    assert all(stream.is_decodable for stream in result.streams)
    assert result.streams[0].kind is MediaStreamKind.VIDEO
    assert calls[0][-3:] == ["-fd", str(source_fd), "fd:"]
    assert call_kwargs[0]["pass_fds"] == (source_fd,)
    assert all("lecture" not in argument for argument in calls[0])


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

    with TemporaryFile("w+b") as source, pytest.raises(MediaProbeError) as captured:
        FfprobeMediaProbe().probe(source)

    assert captured.value.code is MediaProbeFailureCode.NO_DECODABLE_AUDIO
    assert "path" not in captured.value.user_message.lower()


def test_probe_accepts_codec_alias_advertised_by_installed_decoder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "streams": [
            {
                "index": 0,
                "codec_type": "audio",
                "codec_name": "dts",
            }
        ],
        "format": {"format_name": "dts"},
    }

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        stdout = _DECODERS if "-decoders" in command else json.dumps(payload)
        return _completed(command, stdout=stdout)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with TemporaryFile("w+b") as source:
        result = FfprobeMediaProbe().probe(source)

    assert result.audio_streams[0].codec_name == "dts"
    assert result.audio_streams[0].is_decodable


@pytest.mark.parametrize("duration", ["1e1000000", "9223372036854775.808"])
def test_probe_ignores_extreme_duration_without_leaking_decimal_errors(
    monkeypatch: pytest.MonkeyPatch,
    duration: str,
) -> None:
    payload = {
        "streams": [
            {
                "index": 0,
                "codec_type": "audio",
                "codec_name": "aac",
            }
        ],
        "format": {"format_name": "m4a", "duration": duration},
    }

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        stdout = _DECODERS if "-decoders" in command else json.dumps(payload)
        return _completed(command, stdout=stdout)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with TemporaryFile("w+b") as source:
        result = FfprobeMediaProbe().probe(source)

    assert result.duration_ms is None


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
def test_probe_maps_subprocess_failures_to_safe_errors(
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

    with TemporaryFile("w+b") as source, pytest.raises(MediaProbeError) as captured:
        FfprobeMediaProbe().probe(source)

    assert captured.value.code is expected_code
    assert "descriptor" not in str(captured.value).lower()


def test_probe_rejects_malformed_json_as_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        return _completed(command, stdout="{")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with TemporaryFile("w+b") as source, pytest.raises(MediaProbeError) as captured:
        FfprobeMediaProbe().probe(source)

    assert captured.value.code is MediaProbeFailureCode.INVALID_RESPONSE


def test_probe_rejects_a_seekable_stream_without_an_os_descriptor() -> None:
    with pytest.raises(MediaProbeError) as captured:
        FfprobeMediaProbe().probe(BytesIO(b"media"))

    assert captured.value.code is MediaProbeFailureCode.INVALID_MEDIA
    assert "descriptor" not in captured.value.user_message.lower()
