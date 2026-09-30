"""ElevenLabs Scribe behind a fake transport, for the shared provider contract."""

import json

from voz.application.ports.transcription import (
    TranscriptionOptions,
    TranscriptionProvider,
)
from voz.infrastructure.cloud.elevenlabs_scribe import (
    ElevenLabsScribeProvider,
    elevenlabs_scribe_descriptor,
)
from voz.infrastructure.cloud.elevenlabs_transport import HttpRequest, HttpResponse

_PAYLOAD = {
    "language_code": "spa",
    "words": [
        {"text": "hola", "start": 0.0, "end": 0.1, "type": "word", "speaker_id": "a"},
        {"text": " ", "start": 0.1, "end": 1.0, "type": "spacing"},
        {"text": "mundo", "start": 1.0, "end": 1.25, "type": "word", "speaker_id": "a"},
    ],
}


class _Secrets:
    def get(self, provider_id: str) -> str | None:
        return "contract-key"

    def configured(self, provider_id: str) -> bool:
        return True

    def set(self, provider_id: str, key: str) -> None:
        raise AssertionError

    def delete(self, provider_id: str) -> None:
        raise AssertionError


def _transport(request: HttpRequest) -> HttpResponse:
    while request.body.read(4096):
        pass
    return HttpResponse(200, json.dumps(_PAYLOAD).encode())


def elevenlabs_contract_case() -> tuple[TranscriptionProvider, TranscriptionOptions]:
    """Provider (fake transport, never billable) and options for the contract."""
    return (
        ElevenLabsScribeProvider(secrets=_Secrets(), transport=_transport),
        TranscriptionOptions(model=elevenlabs_scribe_descriptor(), language="es"),
    )
