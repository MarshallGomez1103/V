"""A compatible server answering with more audio than allowed is refused."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from openai_compatible_fake import (
    TTS_MODEL,
    VOICES,
    FakeServer,
    fake_server,
    setup,
)

from voz.application.ports.speech_synthesis import SynthesisError, SynthesisFailureCode
from voz.domain.entities.model_descriptor import ModelCapability
from voz.infrastructure.cloud import openai_compatible


@pytest.fixture
def server() -> Generator[FakeServer]:
    with fake_server() as running:
        yield running


def test_oversized_speech_is_a_stable_non_retryable_failure(
    tmp_path: Path, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(openai_compatible, "MAX_SPEECH_BYTES", 100_000)
    configured = setup(tmp_path, server)

    with pytest.raises(SynthesisError) as raised:
        configured.speech().synthesize(
            "Hola " * 400,  # ~0.5 MB of WAV
            model=configured.descriptor(ModelCapability.SYNTHESIS),
            voice_id=VOICES[0],
        )

    assert raised.value.code is SynthesisFailureCode.SYNTHESIS_FAILED
    assert not raised.value.retryable
    assert server.url not in str(raised.value)
    assert TTS_MODEL not in str(raised.value)
