"""Verify that the licensed media fixtures are real, decodable audio."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import TypedDict, cast

import pytest


class _ProbeFormat(TypedDict):
    format_name: str


class _ProbeStream(TypedDict):
    codec_name: str
    codec_type: str


class _ProbePayload(TypedDict):
    format: _ProbeFormat
    streams: list[_ProbeStream]


FIXTURE_DIRECTORY = Path(__file__).parents[2] / "fixtures" / "media"
FIXTURES = (
    (
        "synthetic-tone.wav",
        "wav",
        "pcm_s16le",
        "d959e7258ec4ad502f79a133bee06ccfcd2eac7e7c4ef5040c4829f8c29915ee",
    ),
    (
        "synthetic-tone.mp3",
        "mp3",
        "mp3",
        "8ca7afa2af2e68dde5d8a97abb6a86aef7bc210b040763835cd28df7d5ab0b7d",
    ),
    (
        "synthetic-tone.m4a",
        "m4a",
        "aac",
        "860592365328e72edc49fb5930b76246437fd121efc78a9fc421bd927217fab3",
    ),
    (
        "synthetic-tone.ogg",
        "ogg",
        "vorbis",
        "d9d96e65b0fb292a53868f6a412dcc4ade47e30586bae10822802263823017fd",
    ),
    (
        "synthetic-tone.opus",
        "ogg",
        "opus",
        "3255e94afd95eb8fd68d7072a8d4386db400cd0b776f8d55428a4746227186f7",
    ),
    (
        "synthetic-tone.webm",
        "webm",
        "opus",
        "b673d57f775551995b9d7519c4c0d31372567e5b6c25ce70abbdc69c517cd063",
    ),
)


def _required_executable(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        pytest.fail(f"{name} is required to validate media fixtures")
    return executable


@pytest.mark.parametrize(
    ("filename", "container_name", "codec_name", "expected_sha256"),
    FIXTURES,
    ids=[fixture[0] for fixture in FIXTURES],
)
def test_fixture_is_deterministic_probeable_and_decodable(
    filename: str,
    container_name: str,
    codec_name: str,
    expected_sha256: str,
) -> None:
    fixture = FIXTURE_DIRECTORY / filename
    assert fixture.is_file()
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == expected_sha256

    probe = subprocess.run(
        [
            _required_executable("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=format_name:stream=codec_name,codec_type",
            "-of",
            "json",
            str(fixture),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = cast(_ProbePayload, json.loads(probe.stdout))
    assert container_name in payload["format"]["format_name"].split(",")
    assert any(
        stream["codec_type"] == "audio" and stream["codec_name"] == codec_name
        for stream in payload["streams"]
    )

    subprocess.run(
        [
            _required_executable("ffmpeg"),
            "-v",
            "error",
            "-i",
            str(fixture),
            "-map",
            "0:a:0",
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
    )
