from __future__ import annotations

import io
import logging
import os
import sys
import time
import wave
from dataclasses import replace
from pathlib import Path

import pytest

from voz.application.ports.transcription import (
    TranscriptionClip,
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.quality_profile import QualityProfile, VadSettings
from voz.infrastructure.asr.sherpa_onnx import SherpaOnnxProvider

DESCRIPTOR = ModelDescriptor(
    provider_id="sherpa-onnx-asr",
    model_id="fixture",
    display_name="Whisper ONNX",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION, ModelCapability.CPU}),
)
FAKE = Path(__file__).parents[3] / "fixtures/asr/fake_sherpa_onnx_worker.py"


class Resolver:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def resolve_path(self, descriptor: ModelDescriptor) -> Path:
        assert descriptor == DESCRIPTOR
        return self.directory


def audio(frames: int = 16000) -> io.BytesIO:
    result = io.BytesIO()
    with wave.open(result, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * frames)
    result.seek(0)
    return result


def provider(tmp_path: Path, *, timeout: float = 5) -> SherpaOnnxProvider:
    models = tmp_path / "models"
    models.mkdir(exist_ok=True)
    for name in ("encoder.onnx", "decoder.onnx", "tokens.txt"):
        (models / name).write_bytes(b"fake")
    return SherpaOnnxProvider(
        model_resolver=Resolver(models),
        temp_root=tmp_path / "work",
        worker_argv=(sys.executable, str(FAKE)),
        timeout_seconds=timeout,
    )


def test_fake_child_maps_windows_and_reports_progress(tmp_path: Path) -> None:
    progress: list[int] = []
    result = provider(tmp_path).transcribe(
        audio=audio(31 * 16000),
        options=TranscriptionOptions(
            model=DESCRIPTOR, language="es", on_position=progress.append
        ),
    )
    assert result.text == "hola mundo"
    assert result.language == "es"
    assert [(s.start_ms, s.end_ms) for s in result.segments] == [
        (0, 30000),
        (30000, 31000),
    ]
    assert all(not segment.words for segment in result.segments)
    assert progress == [30000, 31000]
    assert list((tmp_path / "work").iterdir()) == []


def test_clip_is_forwarded_and_native_language_is_not_inferred_from_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_SHERPA_MODE", "no-language")
    result = provider(tmp_path).transcribe(
        audio=audio(35 * 16000),
        options=TranscriptionOptions(
            model=DESCRIPTOR, language="es", clip=TranscriptionClip(1250, 32250)
        ),
    )
    assert result.language is None
    assert [(s.start_ms, s.end_ms) for s in result.segments] == [
        (1250, 31250),
        (31250, 32250),
    ]


@pytest.mark.parametrize(
    "mode",
    ["corrupt", "oversized", "bad-offset", "unsafe-language", "missing-end", "crash"],
)
def test_bad_child_results_are_typed_private_and_cleaned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    mode: str,
) -> None:
    monkeypatch.setenv("FAKE_SHERPA_MODE", mode)
    with caplog.at_level(logging.DEBUG), pytest.raises(TranscriptionError) as failure:
        provider(tmp_path).transcribe(
            audio=audio(), options=TranscriptionOptions(model=DESCRIPTOR)
        )
    assert failure.value.code is TranscriptionFailureCode.PROVIDER_FAILED
    assert "SECRET" not in caplog.text + str(failure.value)
    assert str(tmp_path) not in str(failure.value)
    assert list((tmp_path / "work").iterdir()) == []


def test_timeout_kills_child_and_cleans_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_SHERPA_MODE", "hang")
    start = time.monotonic()
    with pytest.raises(TranscriptionError):
        provider(tmp_path, timeout=0.1).transcribe(
            audio=audio(), options=TranscriptionOptions(model=DESCRIPTOR)
        )
    assert time.monotonic() - start < 3
    assert list((tmp_path / "work").iterdir()) == []


@pytest.mark.parametrize("mode", ["load", "native"])
def test_cancellation_while_child_is_loading_or_decoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    marker = tmp_path / "started"
    monkeypatch.setenv("FAKE_SHERPA_MODE", mode)
    monkeypatch.setenv("FAKE_SHERPA_MARKER", str(marker))

    class Cancel:
        def is_cancelled(self) -> bool:
            return marker.exists()

    with pytest.raises(TranscriptionError) as failure:
        provider(tmp_path).transcribe(
            audio=audio(),
            options=TranscriptionOptions(model=DESCRIPTOR),
            cancellation=Cancel(),
        )
    assert failure.value.code is TranscriptionFailureCode.CANCELLED
    assert list((tmp_path / "work").iterdir()) == []
    if os.name != "nt":
        with pytest.raises(ProcessLookupError):
            os.kill(int(marker.read_text()), 0)


@pytest.mark.parametrize(
    "options",
    [
        TranscriptionOptions(model=DESCRIPTOR, prompt="SECRET"),
        TranscriptionOptions(model=DESCRIPTOR, glossary=("SECRET",)),
        TranscriptionOptions(
            model=DESCRIPTOR,
            quality_profile=QualityProfile(
                "test", 1, 1, (0.0,), False, 0.6, VadSettings()
            ),
        ),
    ],
)
def test_unsupported_options_rejected_before_reading_audio(
    tmp_path: Path, options: TranscriptionOptions
) -> None:
    data = io.BytesIO(b"invalid")
    with pytest.raises(TranscriptionError) as failure:
        provider(tmp_path).transcribe(audio=data, options=options)
    assert failure.value.code is TranscriptionFailureCode.PROVIDER_FAILED
    assert data.tell() == 0 and "SECRET" not in str(failure.value)


def test_invalid_and_truncated_wav_are_rejected_before_child(tmp_path: Path) -> None:
    for data in (io.BytesIO(b"invalid"), io.BytesIO(audio().getvalue()[:-5])):
        with pytest.raises(TranscriptionError) as failure:
            provider(tmp_path).transcribe(
                audio=data, options=TranscriptionOptions(model=DESCRIPTOR)
            )
        assert failure.value.code is TranscriptionFailureCode.INVALID_AUDIO


def test_wrong_provider_and_missing_model_are_typed(tmp_path: Path) -> None:
    runtime = provider(tmp_path)
    with pytest.raises(TranscriptionError) as failure:
        runtime.transcribe(
            audio=audio(),
            options=TranscriptionOptions(
                model=replace(DESCRIPTOR, provider_id="other")
            ),
        )
    assert failure.value.code is TranscriptionFailureCode.MODEL_NOT_INSTALLED
    (tmp_path / "models/encoder.onnx").unlink()
    with pytest.raises(TranscriptionError) as failure:
        runtime.transcribe(
            audio=audio(), options=TranscriptionOptions(model=DESCRIPTOR)
        )
    assert failure.value.code is TranscriptionFailureCode.MODEL_NOT_INSTALLED
