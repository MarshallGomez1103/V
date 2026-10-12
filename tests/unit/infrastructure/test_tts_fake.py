"""Fake TTS engine specifics beyond the shared contract suite."""

from __future__ import annotations

import pytest

from voz.application.ports import SynthesisError, SynthesisFailureCode
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.infrastructure.tts.fake import FakeSpeechSynthesisProvider, fake_tts_descriptor


def test_output_is_deterministic_and_proportional_to_text() -> None:
    fake = FakeSpeechSynthesisProvider()
    model = fake_tts_descriptor()

    short = fake.synthesize("hola mundo", model=model, voice_id="tone-high")
    again = fake.synthesize("hola mundo", model=model, voice_id="tone-high")
    longer = fake.synthesize("hola mundo " * 4, model=model, voice_id="tone-high")

    assert short == again
    assert short.sample_rate == 16_000
    assert longer.frame_count > 3 * short.frame_count


def test_silence_voice_renders_zeros() -> None:
    audio = FakeSpeechSynthesisProvider().synthesize(
        "hola", model=fake_tts_descriptor(), voice_id="silence"
    )

    assert set(audio.samples) == {0}


@pytest.mark.parametrize(
    "model",
    [
        ModelDescriptor(
            provider_id="other",
            model_id="tone",
            display_name="Other engine",
            capabilities=frozenset({ModelCapability.SYNTHESIS}),
        ),
        ModelDescriptor(
            provider_id="fake-tts",
            model_id="asr",
            display_name="Not a TTS model",
            capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
        ),
    ],
)
def test_foreign_models_are_not_installed(model: ModelDescriptor) -> None:
    with pytest.raises(SynthesisError) as raised:
        FakeSpeechSynthesisProvider().voices(model)

    assert raised.value.code is SynthesisFailureCode.MODEL_NOT_INSTALLED


def test_closed_engine_is_runtime_unavailable() -> None:
    fake = FakeSpeechSynthesisProvider()
    fake.close()

    with pytest.raises(SynthesisError) as raised:
        fake.synthesize("hola", model=fake_tts_descriptor(), voice_id="tone-low")

    assert raised.value.code is SynthesisFailureCode.RUNTIME_UNAVAILABLE


@pytest.mark.parametrize("speed", [0.49, 2.01])
def test_out_of_range_speed_is_rejected(speed: float) -> None:
    with pytest.raises(ValueError, match="speed"):
        FakeSpeechSynthesisProvider().synthesize(
            "hola", model=fake_tts_descriptor(), voice_id="tone-low", speed=speed
        )
