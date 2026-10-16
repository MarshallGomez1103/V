from __future__ import annotations

import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from voz.infrastructure.asr.sherpa_onnx_worker import decode_audio, load_whisper


def wav(path: Path, frames: int, *, rate: int = 16000) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b"\0\0" * frames)


class Recognizer:
    def __init__(self) -> None:
        self.frames: list[int] = []

    def create_stream(self) -> Any:
        def accept(rate: int, samples: Any) -> None:
            assert rate == 16000
            self.frames.append(len(samples))

        return SimpleNamespace(
            accept_waveform=accept, result=SimpleNamespace(text=" hola ", lang="es")
        )

    def decode_stream(self, stream: Any) -> None:
        del stream


def test_native_factory_loads_once_with_explicit_cpu_transcription(
    tmp_path: Path,
) -> None:
    files = {key: tmp_path / key for key in ("encoder", "decoder", "tokens")}
    factory = Mock(return_value=Recognizer())
    load_whisper(files, "es", factory=factory)
    factory.assert_called_once_with(
        encoder=str(files["encoder"]),
        decoder=str(files["decoder"]),
        tokens=str(files["tokens"]),
        language="es",
        task="transcribe",
        provider="cpu",
        num_threads=1,
        debug=False,
        enable_token_timestamps=False,
        enable_segment_timestamps=False,
    )


def test_automatic_language_is_empty_native_hint_not_default_english(
    tmp_path: Path,
) -> None:
    factory = Mock(return_value=Recognizer())
    load_whisper(
        {key: tmp_path / key for key in ("encoder", "decoder", "tokens")},
        factory=factory,
    )
    assert factory.call_args.kwargs["language"] == ""


@pytest.mark.parametrize(
    "frames,expected",
    [(480000, [480000]), (480001, [480000, 1]), (976000, [480000, 480000, 16000])],
)
def test_windows_include_every_sample_and_keep_literal_text(
    tmp_path: Path, frames: int, expected: list[int]
) -> None:
    audio = tmp_path / "audio.wav"
    wav(audio, frames)
    engine = Recognizer()
    events: list[dict[str, object]] = []
    decode_audio(audio, engine, emit=events.append)
    assert engine.frames == expected
    windows = [event for event in events if event["type"] == "segment"]
    assert [event["start_ms"] for event in windows] == [
        i * 30000 for i in range(len(expected))
    ]
    assert windows[-1]["end_ms"] == (frames * 1000 + 15999) // 16000
    assert all(event["text"] == " hola " for event in windows)
    assert events[-1] == {"type": "end", "language": "es"}


def test_clip_offsets_and_partial_window_are_exact(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    wav(audio, 33 * 16000)
    engine = Recognizer()
    events: list[dict[str, object]] = []
    decode_audio(audio, engine, emit=events.append, start_ms=1250, end_ms=32250)
    assert engine.frames == [480000, 16000]
    assert [(e["start_ms"], e["end_ms"]) for e in events if e["type"] == "segment"] == [
        (1250, 31250),
        (31250, 32250),
    ]


@pytest.mark.parametrize("rate", [8000, 44100])
def test_rejects_non_normalized_audio_before_decode(tmp_path: Path, rate: int) -> None:
    audio = tmp_path / "audio.wav"
    wav(audio, 100, rate=rate)
    engine = Recognizer()
    with pytest.raises(ValueError):
        decode_audio(audio, engine, emit=lambda _: None)
    assert not engine.frames


def test_does_not_invent_language_when_native_result_has_none(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    wav(audio, 16000)
    engine = Mock()
    engine.create_stream.return_value.result = SimpleNamespace(
        text="literal", lang="/private/secret"
    )
    events: list[dict[str, object]] = []
    decode_audio(audio, engine, emit=events.append)
    assert events[-1] == {"type": "end", "language": None}
