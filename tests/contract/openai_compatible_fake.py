"""A loopback OpenAI-compatible server (stdlib ``http.server`` in a thread).

Implements ``GET /v1/models``, ``POST /v1/audio/transcriptions`` and
``POST /v1/audio/speech`` well enough for the provider contracts. Nothing is
billable and nothing leaves 127.0.0.1. ``key`` makes every route demand
``Authorization: Bearer <key>``; ``speech_delay_s`` slows ``/audio/speech``
down so cancellation can cut a request in flight.
"""

from __future__ import annotations

import contextlib
import json
import struct
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast

from voz.application.ports.compatible_endpoints import CompatibleEndpoint
from voz.application.ports.transcription import TranscriptionOptions
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.infrastructure.cloud.compatible_store import FileCompatibleEndpointStore
from voz.infrastructure.cloud.openai_compatible import (
    CompatibleSpeechProvider,
    CompatibleTranscriptionProvider,
    model_key,
    provider_id_for,
)
from voz.infrastructure.cloud.openai_transport import urllib_transport
from voz.infrastructure.secrets import ProviderSecrets

SAMPLE_RATE = 24_000
STT_MODEL = "whisper-tiny"
TTS_MODEL = "kokoro"
VOICES = ("af_bella", "ef_dora")


@dataclass
class FakeServer:
    url: str
    key: str | None = None
    speech_delay_s: float = 0.0
    speech_status: int = 200
    speech_format: str = "wav"  # "wav", "wav-streaming", "pcm"
    requests: list[tuple[str, str, dict[str, str], bytes]] = field(
        default_factory=list[tuple[str, str, dict[str, str], bytes]]
    )

    @property
    def base_url(self) -> str:
        return self.url + "/v1"


def wav_bytes(frames: int, *, streaming: bool = False) -> bytes:
    data = b"".join(struct.pack("<h", (i % 50) * 200 - 5000) for i in range(frames))
    size = 0xFFFFFFFF if streaming else len(data)
    header = (
        b"RIFF"
        + struct.pack("<I", 0xFFFFFFFF if streaming else 36 + len(data))
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE, SAMPLE_RATE * 2, 2, 16)
        + b"data"
        + struct.pack("<I", size)
    )
    return header + data


def _handler(server: FakeServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def _reply(
            self, status: int, body: bytes, content_type: str = "application/json"
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            with contextlib.suppress(OSError):  # the client cut it (cancellation)
                self.wfile.write(body)

        def _authorized(self, body: bytes) -> bool:
            headers = {name.lower(): value for name, value in self.headers.items()}
            server.requests.append((self.command, self.path, headers, body))
            if server.key is None:
                return True
            if headers.get("authorization") == f"Bearer {server.key}":
                return True
            self._reply(401, b'{"error": {"message": "bad key"}}')
            return False

        def do_GET(self) -> None:
            if not self._authorized(b""):
                return
            if self.path != "/v1/models":
                self._reply(404, b"{}")
                return
            models = [{"id": STT_MODEL}, {"id": TTS_MODEL}]
            self._reply(200, json.dumps({"object": "list", "data": models}).encode())

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            if not self._authorized(body):
                return
            if self.path == "/v1/audio/transcriptions":
                self._reply(
                    200,
                    json.dumps(
                        {
                            "language": "spanish",
                            "segments": [
                                {"start": 0.0, "end": 0.1, "text": "hola"},
                                {"start": 0.1, "end": 0.25, "text": " mundo"},
                            ],
                        }
                    ).encode(),
                )
            elif self.path == "/v1/audio/speech":
                self._speech(body)
            else:
                self._reply(404, b"{}")

        def _speech(self, body: bytes) -> None:
            if server.speech_delay_s:
                time.sleep(server.speech_delay_s)
            if server.speech_status != 200:
                self._reply(server.speech_status, b'{"error": {}}')
                return
            payload = cast(dict[str, object], json.loads(body))
            text = cast(str, payload["input"])
            speed = float(cast(float, payload.get("speed", 1.0)))
            frames = max(1, int(len(text) * 240 / speed))
            if server.speech_format == "pcm":
                self._reply(200, wav_bytes(frames)[44:], "audio/pcm")
            else:
                streaming = server.speech_format == "wav-streaming"
                self._reply(200, wav_bytes(frames, streaming=streaming), "audio/wav")

    return Handler


@contextmanager
def fake_server(key: str | None = None) -> Generator[FakeServer]:
    holder = FakeServer("", key)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _handler(holder))
    httpd.daemon_threads = True
    holder.url = f"http://127.0.0.1:{httpd.server_address[1]}"
    thread = threading.Thread(
        target=httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    )
    thread.start()
    try:
        yield holder
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


def endpoint_for(server: FakeServer, **changes: object) -> CompatibleEndpoint:
    values: dict[str, object] = {
        "id": "0123456789ab",
        "name": "Local test server",
        "base_url": server.base_url,
        "stt_models": (STT_MODEL,),
        "tts_models": (TTS_MODEL,),
        "tts_voices": VOICES,
        **changes,
    }
    return CompatibleEndpoint(**values)  # type: ignore[arg-type]


@dataclass(frozen=True)
class CompatibleSetup:
    store: FileCompatibleEndpointStore
    secrets: ProviderSecrets
    endpoint: CompatibleEndpoint

    def speech(self, **options: float) -> CompatibleSpeechProvider:
        return CompatibleSpeechProvider(
            store=self.store,
            secrets=self.secrets,
            transport=urllib_transport,
            cloud=self.endpoint.cloud,
            **options,
        )

    def transcription(self) -> CompatibleTranscriptionProvider:
        return CompatibleTranscriptionProvider(
            store=self.store,
            secrets=self.secrets,
            transport=urllib_transport,
            cloud=self.endpoint.cloud,
            max_attempts=1,
        )

    def descriptor(self, capability: ModelCapability) -> ModelDescriptor:
        tts = capability is ModelCapability.SYNTHESIS
        model = TTS_MODEL if tts else STT_MODEL
        return ModelDescriptor(
            provider_id=provider_id_for(self.endpoint),
            model_id=model_key(self.endpoint, model),
            display_name=f"Test · {model}",
            capabilities=frozenset({capability}),
        )

    def transcription_options(self) -> TranscriptionOptions:
        return TranscriptionOptions(
            model=self.descriptor(ModelCapability.TRANSCRIPTION), language="es"
        )


def setup(
    config_dir: Path, server: FakeServer, *, key: str | None = None
) -> CompatibleSetup:
    store = FileCompatibleEndpointStore(config_dir)
    secrets = ProviderSecrets(config_dir, environ={})
    endpoint = endpoint_for(server)
    store.save(endpoint)
    if key is not None:
        secrets.set(endpoint.secret_id, key)
    return CompatibleSetup(store, secrets, endpoint)


__all__ = [
    "SAMPLE_RATE",
    "STT_MODEL",
    "TTS_MODEL",
    "VOICES",
    "CompatibleSetup",
    "FakeServer",
    "endpoint_for",
    "fake_server",
    "setup",
    "wav_bytes",
]
