"""Contract tests for the diarization port."""

from __future__ import annotations

import io
from typing import BinaryIO

import pytest

from voz.application.ports.diarization import (
    DiarizationError,
    DiarizationFailureCode,
    DiarizationOptions,
    DiarizationProvider,
    DiarizationResult,
    DiarizedTurn,
    SpeakerCountHint,
)
from voz.application.ports.transcription import TranscriptionCancellationToken


def test_speaker_count_hint_defaults_to_automatic() -> None:
    assert SpeakerCountHint().is_automatic
    assert DiarizationOptions().speakers.is_automatic


@pytest.mark.parametrize(
    "hint",
    [
        SpeakerCountHint(exact=2),
        SpeakerCountHint(minimum=1),
        SpeakerCountHint(maximum=4),
        SpeakerCountHint(minimum=2, maximum=2),
    ],
)
def test_speaker_count_hint_accepts_valid_forms(hint: SpeakerCountHint) -> None:
    assert not hint.is_automatic


@pytest.mark.parametrize(
    "kwargs",
    [
        {"exact": 0},
        {"minimum": 0},
        {"maximum": -1},
        {"exact": 2, "minimum": 1},
        {"exact": 2, "maximum": 3},
        {"minimum": 3, "maximum": 2},
    ],
)
def test_speaker_count_hint_rejects_invalid_values(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        SpeakerCountHint(**kwargs)


def test_speaker_count_hint_rejects_non_integers() -> None:
    with pytest.raises(TypeError):
        SpeakerCountHint(exact=True)
    with pytest.raises(TypeError):
        SpeakerCountHint(minimum=1.5)  # pyright: ignore[reportArgumentType]


def test_options_reject_non_hint() -> None:
    with pytest.raises(TypeError):
        DiarizationOptions(speakers=2)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize(
    ("start", "end", "cluster"),
    [(-1, 10, "0"), (10, 10, "0"), (10, 5, "0"), (0, 10, " ")],
)
def test_diarized_turn_rejects_invalid_values(
    start: int, end: int, cluster: str
) -> None:
    with pytest.raises(ValueError):
        DiarizedTurn(start, end, cluster)


def test_diarized_turn_and_result_reject_wrong_types() -> None:
    with pytest.raises(TypeError):
        DiarizedTurn(0.5, 10, "0")  # pyright: ignore[reportArgumentType]
    with pytest.raises(TypeError):
        DiarizedTurn(0, 10, 3)  # pyright: ignore[reportArgumentType]
    with pytest.raises(TypeError):
        DiarizationResult(turns=[])  # pyright: ignore[reportArgumentType]
    with pytest.raises(TypeError):
        DiarizationResult(turns=("x",))  # pyright: ignore[reportArgumentType]


def test_result_accepts_unordered_overlapping_turns() -> None:
    turns = (DiarizedTurn(500, 900, "1"), DiarizedTurn(0, 1_000, "0"))
    assert DiarizationResult(turns).turns == turns
    assert DiarizationResult(()).turns == ()


def test_failure_codes_are_stable() -> None:
    assert {code.name: code.value for code in DiarizationFailureCode} == {
        "CANCELLED": "diarization_cancelled",
        "INVALID_AUDIO": "diarization_invalid_audio",
        "MODEL_UNAVAILABLE": "diarization_model_unavailable",
        "RUNTIME_UNAVAILABLE": "diarization_runtime_unavailable",
        "PROVIDER_FAILED": "diarization_provider_failed",
    }


def test_error_carries_code_and_safe_message() -> None:
    error = DiarizationError(DiarizationFailureCode.MODEL_UNAVAILABLE, "Falta modelo")
    assert error.code is DiarizationFailureCode.MODEL_UNAVAILABLE
    assert error.user_message == str(error) == "Falta modelo"
    assert not error.retryable


class _FakeProvider:
    provider_id = "fake"

    def diarize(
        self,
        *,
        audio: BinaryIO,
        options: DiarizationOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> DiarizationResult:
        if cancellation is not None and cancellation.is_cancelled():
            raise DiarizationError(DiarizationFailureCode.CANCELLED, "Cancelado")
        return DiarizationResult((DiarizedTurn(0, 10, "0"),))


class _Cancelled:
    def is_cancelled(self) -> bool:
        return True


def test_provider_protocol_is_structural() -> None:
    provider: DiarizationProvider = _FakeProvider()
    assert isinstance(provider, DiarizationProvider)
    result = provider.diarize(audio=io.BytesIO(b""), options=DiarizationOptions())
    assert result.turns == (DiarizedTurn(0, 10, "0"),)
    with pytest.raises(DiarizationError) as caught:
        provider.diarize(
            audio=io.BytesIO(b""),
            options=DiarizationOptions(),
            cancellation=_Cancelled(),
        )
    assert caught.value.code is DiarizationFailureCode.CANCELLED
