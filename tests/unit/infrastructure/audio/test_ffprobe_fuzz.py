"""Seeded fuzzing of ffprobe payloads through the adapter and import metadata.

Invariant: malformed or extreme probe output either yields valid metadata or a
typed ``MediaProbeError`` (or ``MediaNormalizationError`` downstream), never a
raw ``KeyError``/``TypeError``/``ValueError``/``ArithmeticError``.
"""

from __future__ import annotations

import json
import random
import subprocess
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryFile
from typing import BinaryIO
from uuid import UUID

import pytest

from voz.application.import_media import ImportMedia
from voz.application.normalize_media import NormalizeImportedMedia
from voz.application.ports.media_normalization import (
    MediaNormalizationError,
    NormalizedAudio,
)
from voz.application.ports.media_probe import (
    MediaProbeError,
    MediaProbeResult,
    MediaStreamKind,
)
from voz.application.ports.media_storage import ImportedOriginal
from voz.domain.entities.media_asset import MediaAsset
from voz.infrastructure.audio.ffprobe import FfprobeMediaProbe

SEEDS = (1, 7, 42, 2026, 31337)
PAYLOADS_PER_SEED = 300

_DECODERS = """\
Decoders:
 ------
 V....D h264                 H.264
 A....D aac                  AAC
 A....D dca                  DCA (DTS Coherent Acoustics) (codec dts)
 A....D pcm_s16le            PCM signed 16-bit little-endian
 A....D opus                 Opus (codec opus)
"""

_HUGE_DIGITS = "9" * 5_000
# Markers replaced after json.dumps so the raw text can hold values Python's
# json encoder cannot produce (huge ints, out-of-range floats).
_RAW = {
    '"<HUGE_NUM>"': _HUGE_DIGITS,
    '"<HUGE_STR>"': f'"{_HUGE_DIGITS}"',
    '"<E400>"': "1e400",
    '"<NEG_E400>"': "-1e400",
    '"<DEEP>"': "[" * 5_000 + "]" * 5_000,
}
_NUMBERS: tuple[int | float, ...] = (
    0,
    1,
    -1,
    2,
    48_000,
    2**31,
    2**63 - 1,
    2**63,
    -(2**63),
    10**30,
    10**400,
    0.0,
    -0.0,
    0.001,
    1e308,
    5e-324,
    float("nan"),
    float("inf"),
    float("-inf"),
)
_STRINGS = (
    "",
    " ",
    "0",
    "-1",
    "1.5",
    "4.125",
    "48000",
    "nan",
    "NaN",
    "inf",
    "-inf",
    "1e999999999",
    "1e-999999999",
    "-1e9",
    "9" * 40,
    "0x10",
    "1_000",
    "12.5.3",
    "\uff11\uff12\uff13",  # fullwidth digits
    "\u0661\u0662\u0663",  # arabic-indic digits
    "\x00",
    "‮",
    "🎧",
    "ñandú",
    "aac",
    "AAC",
    " aac ",
    "aac\n",
    "pcm_s16le",
    "opus",
    "h264",
    "none",
    "unknown",
    "audio",
    "video",
    "subtitle",
    "data",
    "webm",
    "mov,mp4,m4a",
    ",,,",
    "a" * 10_000,
    "matroska,webm",
    "<HUGE_NUM>",
    "<HUGE_STR>",
    "<E400>",
    "<NEG_E400>",
    "<DEEP>",
)
_STREAM_KEYS = ("index", "codec_type", "codec_name", "sample_rate", "channels")


def _value(rng: random.Random, depth: int = 0) -> object:
    kind = rng.randrange(8 if depth < 2 else 5)
    if kind == 0:
        return None
    if kind == 1:
        return rng.random() < 0.5
    if kind == 2:
        return rng.choice(_NUMBERS)
    if kind in (3, 4):
        return rng.choice(_STRINGS)
    if kind == 5:
        return [_value(rng, depth + 1) for _ in range(rng.randrange(4))]
    if kind == 6:
        return {
            str(rng.choice(_STRINGS)): _value(rng, depth + 1)
            for _ in range(rng.randrange(4))
        }
    return {}


def _stream(rng: random.Random) -> object:
    if rng.random() < 0.1:
        return _value(rng)
    stream: dict[str, object] = {
        "index": rng.randrange(4),
        "codec_type": rng.choice(["audio", "audio", "video", "subtitle"]),
        "codec_name": rng.choice(["aac", "pcm_s16le", "h264", "opus", "mystery"]),
        "sample_rate": rng.choice(["48000", "16000", 44_100]),
        "channels": rng.choice([1, 2, 6]),
    }
    for key in _STREAM_KEYS:
        roll = rng.random()
        if roll < 0.2:
            del stream[key]
        elif roll < 0.55:
            stream[key] = _value(rng)
    if rng.random() < 0.1:
        stream[str(rng.choice(_STRINGS))] = _value(rng)
    return stream


def _payload_text(rng: random.Random) -> str:
    payload: dict[str, object] = {
        "streams": [_stream(rng) for _ in range(rng.randrange(4))],
        "format": {
            "format_name": rng.choice(["wav", "mov,mp4,m4a", "matroska,webm", "ogg"]),
            "duration": rng.choice(["0.25", "4.125", 12.5, "3600"]),
        },
    }
    format_data = payload["format"]
    assert isinstance(format_data, dict)
    roll = rng.random()
    if roll < 0.08:
        payload["streams"] = _value(rng)
    elif roll < 0.12:
        del payload["streams"]
    if rng.random() < 0.3:
        format_data["duration"] = _value(rng)
    if rng.random() < 0.3:
        format_data["format_name"] = _value(rng)
    if rng.random() < 0.1:
        payload["format"] = _value(rng)
    if rng.random() < 0.05:
        return json.dumps(_value(rng))
    text = json.dumps(payload, ensure_ascii=rng.random() < 0.5)
    for marker, raw in _RAW.items():
        text = text.replace(marker, raw)
    if rng.random() < 0.05:
        text = text[: rng.randrange(len(text) + 1)]
    return text


def _probe_with(
    monkeypatch: pytest.MonkeyPatch, stdout: str, decoders: str = _DECODERS
) -> MediaProbeResult:
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout, decoders))
    with TemporaryFile("w+b") as source:
        return FfprobeMediaProbe().probe(source)


def _assert_valid_metadata(result: MediaProbeResult) -> None:
    assert result.duration_ms is None or (
        type(result.duration_ms) is int and 0 < result.duration_ms < 2**63
    )
    assert any(
        s.kind is MediaStreamKind.AUDIO and s.is_decodable for s in result.streams
    )
    for stream in result.streams:
        assert type(stream.index) is int and stream.index >= 0
        for value in (stream.sample_rate_hz, stream.channels):
            assert value is None or (type(value) is int and value > 0)


class _Storage:
    """In-memory storage: enough for ``ImportMedia`` to build a ``MediaAsset``."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def import_original(
        self,
        *,
        source: Path,
        project_id: UUID,
        media_asset_id: UUID,
        media_type: str | None = None,
    ) -> ImportedOriginal:
        asset = MediaAsset(
            project_id, "a" * 64, "x.bin", 1, id=media_asset_id, media_type=media_type
        )
        return ImportedOriginal(asset, 1)

    def open_original(self, *, project_id: UUID, media_asset_id: UUID) -> BinaryIO:
        return self.path.open("rb")

    def discard_original(self, *, project_id: UUID, media_asset_id: UUID) -> None:
        return None


class _Assets:
    def __init__(self) -> None:
        self.stored: list[MediaAsset] = []

    def add(self, media_asset: MediaAsset) -> None:
        self.stored.append(media_asset)

    def get(self, media_asset_id: UUID) -> MediaAsset | None:
        return next((a for a in self.stored if a.id == media_asset_id), None)


class _Normalizer:
    def normalize(self, **kwargs: object) -> NormalizedAudio:
        return NormalizedAudio(bytes_written=44)


def _run_pipeline(monkeypatch: pytest.MonkeyPatch, stdout: str, tmp_path: Path) -> bool:
    """Probe -> import -> normalize; return whether the payload was accepted."""
    project_id = UUID(int=1)
    source = tmp_path / "x.bin"
    source.write_bytes(b"x")
    monkeypatch.setattr(subprocess, "run", _fake_run(stdout))
    assets = _Assets()
    storage = _Storage(source)
    try:
        imported = ImportMedia(
            media_probe=FfprobeMediaProbe(),
            media_storage=storage,  # type: ignore[arg-type]
            media_assets=assets,  # type: ignore[arg-type]
        ).execute(source=source, project_id=project_id)
    except MediaProbeError:
        assert assets.stored == []
        return False
    _assert_valid_metadata(imported.probe_result)
    assert imported.media_asset.duration_ms == imported.probe_result.duration_ms
    with suppress(MediaNormalizationError):
        NormalizeImportedMedia(
            media_storage=storage,  # type: ignore[arg-type]
            media_normalization=_Normalizer(),  # type: ignore[arg-type]
        ).execute(imported_media=imported)
    return True


def _fake_run(
    stdout: str, decoders: str = _DECODERS
) -> Callable[..., subprocess.CompletedProcess[str]]:
    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        text = decoders if "-decoders" in command else stdout
        return subprocess.CompletedProcess(command, 0, text, "")

    return fake_run


@pytest.mark.parametrize("seed", SEEDS)
def test_fuzzed_probe_payloads_yield_metadata_or_typed_error(
    seed: int, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rng = random.Random(seed)
    accepted = 0
    for _ in range(PAYLOADS_PER_SEED):
        text = _payload_text(rng)
        try:
            accepted += _run_pipeline(monkeypatch, text, tmp_path)
        except Exception as error:
            pytest.fail(f"{type(error).__name__} leaked for payload {text[:300]!r}")
    # The generator must exercise both outcomes, not only rejections.
    assert 0 < accepted < PAYLOADS_PER_SEED


@pytest.mark.parametrize("seed", SEEDS)
def test_fuzzed_decoder_listings_never_raise_untyped_errors(
    seed: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    rng = random.Random(seed)
    alphabet = " \t\n.()-_abcAV0123456789ñ🎧\x00"
    payload = json.dumps(
        {"streams": [{"index": 0, "codec_type": "audio", "codec_name": "aac"}]}
    )
    for _ in range(PAYLOADS_PER_SEED):
        decoders = "".join(rng.choice(alphabet) for _ in range(rng.randrange(200)))
        if rng.random() < 0.5:
            decoders += "\n A....D aac AAC\n"
        with suppress(MediaProbeError):
            _assert_valid_metadata(_probe_with(monkeypatch, payload, decoders))


@pytest.mark.parametrize(
    "stdout",
    [
        '{"streams": [{"index": 0, "codec_type": "audio", "codec_name": "aac",'
        ' "sample_rate": "' + _HUGE_DIGITS + '"}]}',
        '{"streams": [{"index": ' + _HUGE_DIGITS + ', "codec_type": "audio",'
        ' "codec_name": "aac"}], "format": {"duration": ' + _HUGE_DIGITS + "}}",
        '{"streams": [{"index": 0, "codec_type": "audio", "codec_name": "aac"}],'
        ' "format": {"duration": "' + _HUGE_DIGITS + '"}}',
        "[" * 5_000 + "]" * 5_000,
        "1" + "0" * 5_000,
    ],
    ids=["huge-sample-rate", "huge-index", "huge-duration-string", "deep", "huge-int"],
)
def test_regression_oversized_numbers_never_leak_value_errors(
    stdout: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    try:
        result = _probe_with(monkeypatch, stdout)
    except MediaProbeError:
        return
    _assert_valid_metadata(result)
