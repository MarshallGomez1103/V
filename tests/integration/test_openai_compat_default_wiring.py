"""Compatible HTTP calls reuse the default local jobs with fake speech engines."""

from __future__ import annotations

import io
import wave
from pathlib import Path
from typing import BinaryIO, cast

import httpx
import pytest
from fastapi.testclient import TestClient

import voz.bootstrap as bootstrap
from voz.application.asr_device_selection import HardwareCapabilities
from voz.application.get_transcription_options import GetTranscriptionOptions
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionOptions,
    TranscriptionResult,
    TranscriptionSegment,
)
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
    RuntimeAvailability,
)
from voz.application.transcription_provider_registry import (
    TranscriptionProviderRegistry,
)
from voz.domain.entities.processing_profile import ComputePrecision
from voz.infrastructure.asr.catalog import faster_whisper_catalog
from voz.infrastructure.tts.fake import FakeSpeechSynthesisProvider, fake_tts_descriptor

MODEL = faster_whisper_catalog()[0].descriptor
MODEL_KEY = f"{MODEL.provider_id}:{MODEL.model_id}"
WAV = Path(__file__).parents[1] / "fixtures/media/synthetic-tone.wav"


class Catalog:
    def list_models(self) -> tuple[ModelRegistration, ...]:
        return (ModelRegistration(MODEL, InstallationStatus.REGISTERED, True),)


class TtsCatalog:
    def list_models(self) -> tuple[ModelRegistration, ...]:
        return (
            ModelRegistration(
                fake_tts_descriptor(), InstallationStatus.REGISTERED, True
            ),
        )


class Runtime:
    def probe(self, provider_id: str) -> RuntimeAvailability:
        return RuntimeAvailability(
            True,
            HardwareCapabilities(frozenset(), frozenset({ComputePrecision.INT8})),
            MODEL.capabilities,
        )


class Provider:
    provider_id = "faster-whisper"

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        assert audio.read(4) == b"RIFF"
        return TranscriptionResult((TranscriptionSegment(0, 250, "hola local"),), "es")


class LocalRuntime:
    providers = TranscriptionProviderRegistry([Provider()])

    def close(self) -> None:
        pass


def test_default_wiring_lists_and_transcribes_local_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def local_runtime(*_args: object, **_kwargs: object) -> LocalRuntime:
        return LocalRuntime()

    monkeypatch.setattr(bootstrap, "create_local_asr_runtime", local_runtime)
    options = GetTranscriptionOptions(Catalog(), Runtime())
    with TestClient(bootstrap.create_app(transcription_options=options)) as raw:
        client = cast(httpx.Client, raw)
        models = client.get("/v1/models")
        assert models.status_code == 200
        assert any(m["id"] == MODEL_KEY for m in models.json()["data"])
        response = client.post(
            "/v1/audio/transcriptions",
            data={"model": MODEL_KEY, "language": "es"},
            files={"file": ("test.wav", WAV.read_bytes(), "audio/wav")},
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"text": "hola local"}
        assert client.get("/api/library").status_code == 200


def test_default_wiring_speech_returns_real_wav_from_fake_runner() -> None:
    with TestClient(
        bootstrap.create_app(
            synthesis_providers=[FakeSpeechSynthesisProvider()],
            synthesis_catalog=TtsCatalog(),
        )
    ) as raw:
        client = cast(httpx.Client, raw)
        response = client.post(
            "/v1/audio/speech",
            json={
                "model": "fake-tts:tone",
                "input": "Local synthetic speech.",
                "voice": "tone-low",
            },
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("audio/wav")
        with wave.open(io.BytesIO(response.content), "rb") as audio:
            assert audio.getnframes() > 0 and audio.getframerate() == 16000


def test_default_compatible_speech_enforces_server_credentials() -> None:
    token = "a" * 43
    with TestClient(
        bootstrap.create_app(
            auth_token=token,
            synthesis_providers=[FakeSpeechSynthesisProvider()],
            synthesis_catalog=TtsCatalog(),
        )
    ) as raw:
        client = cast(httpx.Client, raw)
        body = {
            "model": "fake-tts:tone",
            "input": "Authorized local audio.",
            "voice": "tone-low",
            "response_format": "wav",
        }
        assert client.get("/v1/models").status_code == 401
        assert client.post("/v1/audio/speech", json=body).status_code == 401
        authorized = client.post(
            "/v1/audio/speech", json=body, headers={"Authorization": "Bearer " + token}
        )
        assert authorized.status_code == 200 and authorized.content.startswith(b"RIFF")
