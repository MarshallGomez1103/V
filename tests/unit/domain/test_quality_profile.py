"""QualityProfile is an immutable, validated, round-trippable recipe (S13.02)."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace

import pytest

from voz.domain.entities.quality_profile import QualityProfile, VadSettings

PROFILE = QualityProfile(
    name="academic",
    version=2,
    beam_size=5,
    temperature=(0.0, 0.2),
    condition_on_previous_text=False,
    no_speech_threshold=0.6,
    vad=VadSettings(0.4, 250, 1000, 300),
)


def test_round_trips_through_json_exactly() -> None:
    restored = QualityProfile.from_dict(json.loads(json.dumps(PROFILE.to_dict())))

    assert restored == PROFILE
    no_vad = replace(PROFILE, vad=None)
    assert QualityProfile.from_dict(no_vad.to_dict()) == no_vad


def test_is_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        PROFILE.beam_size = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    "change",
    [
        {"name": "Bad Name"},
        {"name": ""},
        {"version": 0},
        {"beam_size": 0},
        {"beam_size": 11},
        {"temperature": ()},
        {"temperature": (1.5,)},
        {"temperature": (float("nan"),)},
        {"no_speech_threshold": 2.0},
    ],
)
def test_rejects_out_of_range_values(change: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        replace(PROFILE, **change)  # type: ignore[arg-type]


def test_rejects_wrong_types() -> None:
    with pytest.raises(TypeError):
        replace(PROFILE, beam_size="5")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        replace(PROFILE, condition_on_previous_text=1)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        QualityProfile.from_dict({**PROFILE.to_dict(), "temperature": "0.0"})


@pytest.mark.parametrize(
    "kwargs",
    [
        {"threshold": 0.0},
        {"threshold": 1.0},
        {"speech_pad_ms": -1},
        {"min_silence_duration_ms": 0},
    ],
)
def test_vad_settings_reject_out_of_range_values(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        VadSettings(**kwargs)  # type: ignore[arg-type]
