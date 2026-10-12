"""Unit tests for provider-neutral model descriptors."""

import pytest

from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor


def test_model_descriptor_is_immutable_and_exposes_stable_identity() -> None:
    descriptor = ModelDescriptor(
        provider_id="local-asr",
        model_id="family/model-v1",
        display_name="Model V1",
        capabilities=frozenset(
            {
                ModelCapability.TRANSCRIPTION,
                ModelCapability.LANGUAGE_DETECTION,
                ModelCapability.CPU,
            }
        ),
    )

    assert descriptor.identity == ("local-asr", "family/model-v1")
    assert descriptor.supports(ModelCapability.TRANSCRIPTION)
    assert not descriptor.supports(ModelCapability.GPU)
    with pytest.raises(AttributeError):
        descriptor.display_name = "Changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("provider_id", "", "provider_id must be a non-empty trimmed identifier"),
        (
            "provider_id",
            " Local ",
            "provider_id must be a non-empty trimmed identifier",
        ),
        ("provider_id", "local/provider", "provider_id must be a safe identifier"),
        ("model_id", "", "model_id must be a non-empty trimmed string"),
        ("model_id", " model ", "model_id must be a non-empty trimmed string"),
        ("model_id", "model\nsecret", "model_id cannot contain control characters"),
        ("display_name", "", "display_name must be a non-empty trimmed string"),
        ("display_name", " Model ", "display_name must be a non-empty trimmed string"),
    ],
)
def test_model_descriptor_rejects_unsafe_or_ambiguous_text(
    field_name: str,
    value: str,
    message: str,
) -> None:
    values: dict[str, object] = {
        "provider_id": "local-asr",
        "model_id": "family/model-v1",
        "display_name": "Model V1",
        "capabilities": frozenset({ModelCapability.TRANSCRIPTION}),
    }
    values[field_name] = value

    with pytest.raises(ValueError, match=message):
        ModelDescriptor(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("field_name", ["provider_id", "model_id", "display_name"])
def test_model_descriptor_rejects_non_string_text(field_name: str) -> None:
    values: dict[str, object] = {
        "provider_id": "local-asr",
        "model_id": "family/model-v1",
        "display_name": "Model V1",
        "capabilities": frozenset({ModelCapability.TRANSCRIPTION}),
    }
    values[field_name] = 42

    with pytest.raises(TypeError, match=f"{field_name} must be a string"):
        ModelDescriptor(**values)  # type: ignore[arg-type]


def test_model_descriptor_requires_a_frozen_non_empty_capability_set() -> None:
    with pytest.raises(TypeError, match="capabilities must be a frozenset"):
        ModelDescriptor(
            provider_id="local-asr",
            model_id="model",
            display_name="Model",
            capabilities={ModelCapability.TRANSCRIPTION},  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="at least one capability"):
        ModelDescriptor(
            provider_id="local-asr",
            model_id="model",
            display_name="Model",
            capabilities=frozenset(),
        )

    with pytest.raises(TypeError, match="ModelCapability instances"):
        ModelDescriptor(
            provider_id="local-asr",
            model_id="model",
            display_name="Model",
            capabilities=frozenset({"transcription"}),  # type: ignore[arg-type]
        )


def test_capability_vocabulary_remains_provider_neutral() -> None:
    assert {capability.value for capability in ModelCapability} == {
        "transcription",
        "translation",
        "word_timestamps",
        "diarization",
        "synthesis",
        "alignment",
        "wake_word",
        "language_detection",
        "realtime",
        "gpu",
        "cpu",
    }


def test_model_descriptor_exposes_only_complete_pinned_provenance() -> None:
    descriptor = ModelDescriptor(
        provider_id="faster-whisper",
        model_id="large-v3",
        display_name="Large v3",
        capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
        source="Systran/faster-whisper-large-v3",
        revision="0123456789abcdef0123456789abcdef01234567",
    )

    assert descriptor.provenance == (
        "Systran/faster-whisper-large-v3",
        "0123456789abcdef0123456789abcdef01234567",
    )

    with pytest.raises(ValueError, match="provided together"):
        ModelDescriptor(
            provider_id="faster-whisper",
            model_id="large-v3",
            display_name="Large v3",
            capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
            source="Systran/faster-whisper-large-v3",
        )

    with pytest.raises(ValueError, match="40-character lowercase commit SHA"):
        ModelDescriptor(
            provider_id="faster-whisper",
            model_id="large-v3",
            display_name="Large v3",
            capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
            source="Systran/faster-whisper-large-v3",
            revision="main",
        )
