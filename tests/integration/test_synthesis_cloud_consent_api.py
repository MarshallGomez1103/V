"""``POST /api/synthesis`` fails closed for a cloud engine without consent."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from voz.application.ports.speech_synthesis import (
    PcmAudio,
    SynthesisLocality,
    SynthesisProviderInfo,
)
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
)
from voz.bootstrap import create_app
from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.infrastructure.paths import VozPaths
from voz.infrastructure.tts.fake import (
    FAKE_TTS_PROVIDER_ID,
    FakeSpeechSynthesisProvider,
    fake_tts_descriptor,
)

BODY: dict[str, Any] = {
    "text": "Hello there.",
    "provider_id": FAKE_TTS_PROVIDER_ID,
    "model_id": "tone",
    "voice_id": "tone-low",
}


class _CloudTts(FakeSpeechSynthesisProvider):
    def __init__(self) -> None:
        super().__init__(max_chunk_chars=20)
        self.rendered = 0

    def describe(self) -> SynthesisProviderInfo:
        return SynthesisProviderInfo(
            provider_id=FAKE_TTS_PROVIDER_ID,
            display_name="Fake cloud TTS",
            locality=SynthesisLocality.CLOUD,
            max_chunk_chars=20,
        )

    def synthesize(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, chunk_text: str, *, model: ModelDescriptor, **kwargs: Any
    ) -> PcmAudio:
        self.rendered += 1
        return super().synthesize(chunk_text, model=model, **kwargs)


class _Catalog:
    def list_models(self) -> tuple[ModelRegistration, ...]:
        return (
            ModelRegistration(
                fake_tts_descriptor(), InstallationStatus.REGISTERED, True
            ),
        )


def _client(tmp_path: Path, engine: FakeSpeechSynthesisProvider) -> TestClient:
    for name in ("data", "state"):
        (tmp_path / name).mkdir(exist_ok=True)
    paths = VozPaths(
        tmp_path / "config", tmp_path / "data", tmp_path / "cache", tmp_path / "state"
    )
    return TestClient(
        create_app(
            paths=paths,
            synthesis_providers=[engine],
            synthesis_catalog=_Catalog(),
        )
    )


def test_cloud_engine_without_consent_is_refused_and_nothing_is_created(
    tmp_path: Path,
) -> None:
    engine = _CloudTts()
    with _client(tmp_path, engine) as client:
        for extra in ({}, {"cloud_consent": False}):
            response = client.post("/api/synthesis", json={**BODY, **extra})

            assert response.status_code == 422
            assert response.json()["detail"]["code"] == "cloud_consent_required"
        assert client.get("/api/synthesis").json() == {"items": []}
    assert engine.rendered == 0


@pytest.mark.parametrize("value", ["true", 1, "yes"])
def test_consent_must_be_a_real_boolean(tmp_path: Path, value: object) -> None:
    engine = _CloudTts()
    with _client(tmp_path, engine) as client:
        response = client.post("/api/synthesis", json={**BODY, "cloud_consent": value})

        assert response.status_code == 422
        assert client.get("/api/synthesis").json() == {"items": []}
    assert engine.rendered == 0


def test_cloud_engine_with_consent_creates_the_job(tmp_path: Path) -> None:
    with _client(tmp_path, _CloudTts()) as client:
        response = client.post("/api/synthesis", json={**BODY, "cloud_consent": True})

        assert response.status_code == 201
        assert response.json()["provider_id"] == FAKE_TTS_PROVIDER_ID


def test_local_engine_needs_no_consent(tmp_path: Path) -> None:
    with _client(tmp_path, FakeSpeechSynthesisProvider(max_chunk_chars=20)) as client:
        assert client.post("/api/synthesis", json=BODY).status_code == 201
