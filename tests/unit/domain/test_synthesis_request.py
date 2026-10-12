from math import inf, nan

import pytest

from voz.domain.entities import SynthesisOutputFormat, SynthesisRequest
from voz.domain.entities.synthesis_request import (
    MAX_SYNTHESIS_SPEED,
    MAX_SYNTHESIS_TEXT_CHARS,
    MIN_SYNTHESIS_SPEED,
)


def make(**overrides: object) -> SynthesisRequest:
    fields: dict[str, object] = {
        "text": "Hola mundo.",
        "provider_id": "engine",
        "model_id": "model",
        "voice_id": "0",
    }
    fields.update(overrides)
    return SynthesisRequest(**fields)  # type: ignore[arg-type]


def test_defaults_follow_the_adr_output_contract() -> None:
    request = make()

    assert request.speed == 1.0
    assert request.output_format is SynthesisOutputFormat.WAV_PCM16_MONO
    assert request.model_revision is None and request.language is None


def test_text_is_trimmed_and_keeps_inner_newlines() -> None:
    assert make(text="  uno.\ndos.  ").text == "uno.\ndos."


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_blank_text_is_rejected(text: str) -> None:
    with pytest.raises(ValueError, match="blank"):
        make(text=text)


def test_text_length_is_capped_after_trimming() -> None:
    assert len(make(text=" " + "a" * MAX_SYNTHESIS_TEXT_CHARS + " ").text) == (
        MAX_SYNTHESIS_TEXT_CHARS
    )
    with pytest.raises(ValueError, match="at most"):
        make(text="a" * (MAX_SYNTHESIS_TEXT_CHARS + 1))


def test_text_rejects_nul_and_non_strings() -> None:
    with pytest.raises(ValueError):
        make(text="a\x00b")
    with pytest.raises(TypeError):
        make(text=b"bytes")


@pytest.mark.parametrize("speed", [MIN_SYNTHESIS_SPEED, 1, MAX_SYNTHESIS_SPEED])
def test_speed_inside_range_is_accepted(speed: float) -> None:
    assert make(speed=speed).speed == float(speed)


@pytest.mark.parametrize("speed", [0.49, 2.01, 0, -1.0, nan, inf])
def test_speed_outside_range_is_rejected(speed: float) -> None:
    with pytest.raises(ValueError, match="speed"):
        make(speed=speed)


@pytest.mark.parametrize("speed", [True, "1.0", None])
def test_speed_must_be_a_real_number(speed: object) -> None:
    with pytest.raises(TypeError):
        make(speed=speed)


@pytest.mark.parametrize("name", ["provider_id", "model_id", "voice_id"])
def test_identifiers_must_not_be_blank(name: str) -> None:
    with pytest.raises(ValueError):
        make(**{name: " "})


@pytest.mark.parametrize("name", ["model_revision", "language"])
def test_optional_fields_are_trimmed_or_rejected_when_blank(name: str) -> None:
    assert getattr(make(**{name: " x "}), name) == "x"
    with pytest.raises(ValueError):
        make(**{name: ""})


def test_output_format_must_be_the_enum() -> None:
    with pytest.raises(TypeError):
        make(output_format="mp3")
