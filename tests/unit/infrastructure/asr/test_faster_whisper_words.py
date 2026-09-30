"""Word timestamp mapping and fallback of the Faster Whisper adapter (S7.04/S7.08)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pytest

from voz.application.asr_device_selection import ComputeDevice, ExecutionDecision
from voz.application.ports.transcription import (
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
    TranscriptionSegment,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import ComputePrecision
from voz.infrastructure.asr.faster_whisper import FasterWhisperProvider

DESCRIPTOR = ModelDescriptor(
    provider_id="faster-whisper",
    model_id="fixture",
    display_name="Fixture model",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION, ModelCapability.CPU}),
    source="example/faster-whisper-fixture",
    revision="0123456789abcdef0123456789abcdef01234567",
)
CPU = ExecutionDecision(ComputeDevice.CPU, ComputePrecision.INT8)


@dataclass
class _W:
    start: float
    end: float
    word: str
    probability: float = 0.9


@dataclass
class _S:
    start: float
    end: float
    text: str
    words: list[_W] | None = None


@dataclass
class _Info:
    language: str | None = "es"


class _Resolver:
    def __init__(self, path: Path) -> None:
        self.path = path

    def resolve_path(self, descriptor: ModelDescriptor) -> Path:
        return self.path


class _Engine:
    def __init__(self, segments: list[_S], *, fail_with_words: bool = False) -> None:
        self.segments = segments
        self.fail_with_words = fail_with_words
        self.flags: list[bool] = []

    def transcribe(
        self,
        audio: BinaryIO,
        *,
        language: str | None,
        word_timestamps: bool,
        clip_timestamps: str | list[float],
    ) -> tuple[Iterable[_S], _Info]:
        del language, clip_timestamps
        assert audio.read() == b"pcm"  # the retry must rewind the audio
        self.flags.append(word_timestamps)
        if word_timestamps and self.fail_with_words:
            raise RuntimeError("alignment exploded at /private/path")
        return iter(self.segments), _Info()


def _provider(tmp_path: Path, engine: _Engine) -> FasterWhisperProvider:
    def factory(
        model_path: str,
        *,
        device: str,
        compute_type: str,
        local_files_only: bool,
    ) -> _Engine:
        del model_path, device, compute_type, local_files_only
        return engine

    return FasterWhisperProvider(
        model_resolver=_Resolver(tmp_path),
        execution=CPU,
        engine_factory=factory,
    )


def _run(
    provider: FasterWhisperProvider, *, words: bool = True
) -> list[TranscriptionSegment]:
    result = provider.transcribe(
        audio=BytesIO(b"pcm"),
        options=TranscriptionOptions(model=DESCRIPTOR, word_timestamps=words),
    )
    return list(result.segments)


def test_words_are_mapped_to_milliseconds_inside_the_segment(tmp_path: Path) -> None:
    engine = _Engine(
        [
            _S(
                1.0,
                2.0,
                " hola mundo",
                [
                    _W(0.9, 1.4, " hola", 0.97),  # starts before the segment
                    _W(1.4, 2.3, " mundo", 1.4),  # ends after it, probability > 1
                ],
            )
        ]
    )

    (segment,) = _run(_provider(tmp_path, engine))

    assert engine.flags == [True]
    assert [(w.start_ms, w.end_ms, w.text) for w in segment.words] == [
        (1_000, 1_400, " hola"),
        (1_400, 2_000, " mundo"),
    ]
    assert [w.probability for w in segment.words] == [0.97, 1.0]


def test_unusable_words_are_skipped_and_none_words_mean_no_words(
    tmp_path: Path,
) -> None:
    engine = _Engine(
        [
            _S(0.0, 1.0, " a b", [_W(0.0, 0.0, " a"), _W(float("nan"), 1.0, " b")]),
            _S(1.0, 2.0, " c", None),  # engine could not align this span
        ]
    )

    first, second = _run(_provider(tmp_path, engine))

    assert first.words == ()
    assert second.words == ()
    assert [s.text for s in (first, second)] == [" a b", " c"]


def test_words_are_not_requested_when_the_caller_disables_them(tmp_path: Path) -> None:
    engine = _Engine([_S(0.0, 1.0, " a", [_W(0.0, 1.0, " a")])])

    (segment,) = _run(_provider(tmp_path, engine), words=False)

    assert engine.flags == [False]
    assert segment.words == ()


def test_alignment_failure_falls_back_to_a_wordless_pass(tmp_path: Path) -> None:
    engine = _Engine([_S(0.0, 1.0, " hola")], fail_with_words=True)

    (segment,) = _run(_provider(tmp_path, engine))

    assert engine.flags == [True, False]
    assert segment.text == " hola"
    assert segment.words == ()


def test_failure_without_words_still_reports_a_safe_provider_error(
    tmp_path: Path,
) -> None:
    engine = _Engine([_S(0.0, 1.0, " hola")], fail_with_words=True)
    engine.fail_with_words = False

    def boom(*args: object, **kwargs: object) -> object:
        raise RuntimeError("failure at /private/path")

    engine.transcribe = boom  # type: ignore[method-assign]

    with pytest.raises(TranscriptionError) as raised:
        _run(_provider(tmp_path, engine))

    assert raised.value.code is TranscriptionFailureCode.PROVIDER_FAILED
    assert "/private" not in raised.value.user_message
