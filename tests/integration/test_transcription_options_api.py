"""HTTP serialization tested through ASGI with application-only fake ports."""

import asyncio
import json
from typing import cast

from fastapi import FastAPI
from starlette.types import Message

from voz.application.get_transcription_options import GetTranscriptionOptions
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
    RuntimeAvailability,
    TranscriptionOptionsUnavailable,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.interfaces.api.transcription_options import create_transcription_options_router


class Catalog:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def list_models(self) -> tuple[ModelRegistration, ...]:
        if self.fail:
            raise TranscriptionOptionsUnavailable("/private/host/path")
        return (
            ModelRegistration(
                ModelDescriptor(
                    provider_id="fake-asr",
                    model_id="known",
                    display_name="Safe fixture",
                    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
                ),
                InstallationStatus.NOT_REGISTERED,
            ),
        )


class Runtime:
    def probe(self, provider_id: str) -> RuntimeAvailability:
        return RuntimeAvailability(
            False, capabilities=frozenset({ModelCapability.TRANSCRIPTION})
        )


async def request(app: FastAPI) -> tuple[int, dict[str, object]]:
    messages: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/transcription-options",
            "raw_path": b"/api/transcription-options",
            "query_string": b"",
            "headers": [],
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1234),
            "root_path": "",
        },
        receive,
        send,
    )
    body = b"".join(message.get("body", b"") for message in messages)
    return int(messages[0]["status"]), cast(dict[str, object], json.loads(body))


def test_endpoint_serializes_canonical_options_without_concrete_infrastructure() -> (
    None
):
    app = FastAPI()
    app.include_router(
        create_transcription_options_router(
            GetTranscriptionOptions(Catalog(), Runtime())
        )
    )
    status, body = asyncio.run(request(app))
    assert status == 200
    options = cast(list[dict[str, object]], body["options"])
    option = options[0]
    assert option["provider_id"] == "fake-asr"
    assert option["installation_status"] == "not_registered"
    assert option["runtime_available"] is False
    assert option["can_start"] is False
    assert option["revision"] is None
    assert option["recommendation"] is None
    assert option["execution"] is None
    assert option["capabilities"] == ["transcription"]
    assert "runtime_unavailable" in cast(list[str], option["blocking_reasons"])
    assert "/private/" not in json.dumps(body)


def test_endpoint_translates_inspection_error_without_paths() -> None:
    app = FastAPI()
    app.include_router(
        create_transcription_options_router(
            GetTranscriptionOptions(Catalog(True), Runtime())
        )
    )
    status, body = asyncio.run(request(app))
    assert status == 503
    assert body == {
        "detail": {
            "code": "transcription_options_unavailable",
            "message": "Transcription options could not be inspected.",
        }
    }
