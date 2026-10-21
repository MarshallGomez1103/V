"""HTTP compatibility boundaries exercised without inference or network."""

from __future__ import annotations

import io
import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.types import Message

from voz.application.ports.compatible_audio import (
    CompatibleAudioError,
    CompatibleModel,
    CompatibleSpeech,
    CompatibleTranscript,
    CompatibleTranscription,
)
from voz.application.ports.transcription import TranscriptionSegment
from voz.interfaces.api.openai_compat import create_openai_compat_router


class FakeService:
    def __init__(self) -> None:
        self.sources: list[Path] = []
        self.audio = io.BytesIO(b"RIFFsyntheticWAVE")
        self.error: Exception | None = None

    def models(self) -> tuple[CompatibleModel, ...]:
        return (CompatibleModel("local", "V", ("transcription", "speech")),)

    def transcribe(
        self, request: CompatibleTranscription, *, cancelled: Callable[[], bool]
    ) -> CompatibleTranscript:
        self.sources.append(request.source)
        assert request.source.read_bytes() == b"synthetic"
        if os.name == "posix":
            assert request.source.stat().st_mode & 0o777 == 0o600
            assert request.source.parent.stat().st_mode & 0o777 == 0o700
        if self.error:
            raise self.error
        return CompatibleTranscript(
            "Texto sintético",
            "es",
            1.25,
            (TranscriptionSegment(250, 1000, "Texto sintético"),),
        )

    def speech(
        self, request: CompatibleSpeech, *, cancelled: Callable[[], bool]
    ) -> io.BytesIO:
        assert request.speed == 1.0
        if self.error:
            raise self.error
        return self.audio


@pytest.fixture
def setup(tmp_path: Path) -> tuple[httpx.Client, FakeService, Path]:
    service = FakeService()
    app = FastAPI()
    cache = tmp_path / "cache"
    app.include_router(create_openai_compat_router(service, cache_root=cache))
    return cast(httpx.Client, TestClient(app)), service, cache


def test_models(setup: tuple[httpx.Client, FakeService, Path]) -> None:
    client, _, _ = setup
    assert client.get("/v1/models").json() == {
        "object": "list",
        "data": [
            {
                "id": "local",
                "object": "model",
                "created": 0,
                "owned_by": "V",
                "capabilities": ["transcription", "speech"],
            }
        ],
    }


@pytest.mark.parametrize("format", ["json", "text", "verbose_json"])
def test_transcription_formats_and_cleanup(
    setup: tuple[httpx.Client, FakeService, Path], format: str
) -> None:
    client, service, cache = setup
    response = client.post(
        "/v1/audio/transcriptions",
        data={"model": "local", "response_format": format},
        files={"file": ("clip.wav", b"synthetic", "audio/wav")},
    )
    assert response.status_code == 200
    if format == "text":
        assert response.text == "Texto sintético"
    else:
        assert response.json()["text"] == "Texto sintético"
        if format == "verbose_json":
            assert response.json()["duration"] == 1.25
            assert response.json()["segments"] == [
                {"id": 0, "start": 0.25, "end": 1.0, "text": "Texto sintético"}
            ]
    assert service.sources and not service.sources[0].exists()
    assert list(cache.iterdir()) == []


def test_speech_closes_handle(setup: tuple[httpx.Client, FakeService, Path]) -> None:
    client, service, _ = setup
    response = client.post(
        "/v1/audio/speech",
        json={"model": "local", "input": "synthetic", "voice": "local"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == b"RIFFsyntheticWAVE"
    assert service.audio.closed


@pytest.mark.parametrize(
    "extra",
    [
        {"stream": False},
        {"instructions": "private"},
        {"response_format": "mp3"},
        {"unknown": "private"},
        {"speed": True},
        {"speed": float("inf")},
    ],
)
def test_speech_rejects_unsupported(
    setup: tuple[httpx.Client, FakeService, Path], extra: dict[str, object]
) -> None:
    client, _, _ = setup
    # JSON forbids nonfinite numbers; construct that malformed input explicitly.
    body = {"model": "local", "input": "synthetic", "voice": "local", **extra}

    response = client.post(
        "/v1/audio/speech",
        content=json.dumps(body),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert "private" not in response.text
    assert set(response.json()) == {"error"}


@pytest.mark.parametrize(
    "filename", ["../secret.wav", "C:\\private.wav", "/secret.wav", "clip.exe"]
)
def test_unsafe_filename_rejected(
    setup: tuple[httpx.Client, FakeService, Path], filename: str
) -> None:
    client, service, _ = setup
    response = client.post(
        "/v1/audio/transcriptions",
        data={"model": "local"},
        files={"file": (filename, b"synthetic")},
    )
    assert response.status_code == 400
    assert not service.sources
    assert "secret" not in response.text


@pytest.mark.parametrize(
    "error,status",
    [
        (
            CompatibleAudioError("model_not_found", "Model unavailable.", 404, "model"),
            404,
        ),
        (RuntimeError("/private/secret"), 500),
    ],
)
def test_failure_cleanup(
    setup: tuple[httpx.Client, FakeService, Path], error: Exception, status: int
) -> None:
    client, service, cache = setup
    service.error = error
    response = client.post(
        "/v1/audio/transcriptions",
        data={"model": "local"},
        files={"file": ("clip.wav", b"synthetic")},
    )
    assert response.status_code == status
    assert "private" not in response.text
    assert not service.sources[0].exists()
    assert not list(cache.iterdir())


def raw_multipart(parts: list[tuple[str, bytes]], closing: bool = True) -> bytes:
    body = b"".join(
        b"--boundary\r\n" + header.encode() + b"\r\n\r\n" + payload + b"\r\n"
        for header, payload in parts
    )
    return body + (b"--boundary--\r\n" if closing else b"")


FILE_HEADER = 'Content-Disposition: form-data; name="file"; filename="clip.wav"'
MODEL_HEADER = 'Content-Disposition: form-data; name="model"'


@pytest.mark.parametrize(
    "parts,closing",
    [
        (
            [
                (MODEL_HEADER, b"local"),
                (MODEL_HEADER, b"other"),
                (FILE_HEADER, b"synthetic"),
            ],
            True,
        ),
        (
            [
                (MODEL_HEADER, b"local"),
                (FILE_HEADER, b"synthetic"),
                (FILE_HEADER, b"synthetic"),
            ],
            True,
        ),
        (
            [
                (MODEL_HEADER, b"local"),
                (
                    FILE_HEADER + "\r\nContent-Transfer-Encoding: base64",
                    b"c3ludGhldGlj",
                ),
            ],
            True,
        ),
        (
            [
                (MODEL_HEADER, b"local"),
                (
                    FILE_HEADER + "\r\nContent-Type: multipart/mixed; boundary=inner",
                    b"--inner--",
                ),
            ],
            True,
        ),
        ([(MODEL_HEADER, b"local"), (FILE_HEADER, b"synthetic")], False),
        (
            [
                (MODEL_HEADER, b"local"),
                (FILE_HEADER, b"synthetic"),
                ('Content-Disposition: form-data; name="stream"', b"false"),
            ],
            True,
        ),
        (
            [
                (MODEL_HEADER, b"local"),
                (FILE_HEADER, b"synthetic"),
                ('Content-Disposition: form-data; name="prompt"', b"x" * 8193),
            ],
            True,
        ),
        (
            [
                (MODEL_HEADER, b"local"),
                (FILE_HEADER, b"synthetic"),
                *[
                    (f'Content-Disposition: form-data; name="x{i}"', b"x")
                    for i in range(15)
                ],
            ],
            True,
        ),
        (
            [(MODEL_HEADER + '; name="prompt"', b"local"), (FILE_HEADER, b"synthetic")],
            True,
        ),
        (
            [
                (MODEL_HEADER, b"local"),
                (
                    FILE_HEADER + '\r\nContent-Disposition: form-data; name="file"',
                    b"synthetic",
                ),
            ],
            True,
        ),
    ],
)
def test_malformed_multipart_rejected(
    setup: tuple[httpx.Client, FakeService, Path],
    parts: list[tuple[str, bytes]],
    closing: bool,
) -> None:
    client, service, _ = setup
    response = client.post(
        "/v1/audio/transcriptions",
        content=raw_multipart(parts, closing),
        headers={"content-type": "multipart/form-data; boundary=boundary"},
    )
    assert response.status_code == 400
    assert not service.sources


@pytest.mark.parametrize("target", ["body", "file"])
def test_size_limits(
    setup: tuple[httpx.Client, FakeService, Path],
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    from voz.interfaces.api import openai_compat as api

    client, service, _ = setup
    monkeypatch.setattr(api, "BODY_LIMIT" if target == "body" else "FILE_LIMIT", 8)
    response = client.post(
        "/v1/audio/transcriptions",
        data={"model": "local"},
        files={"file": ("clip.wav", b"synthetic")},
    )
    assert response.status_code == 413
    assert not service.sources


def test_duplicate_json_rejected(setup: tuple[httpx.Client, FakeService, Path]) -> None:
    client, _, _ = setup
    response = client.post(
        "/v1/audio/speech",
        content=b'{"model":"local","model":"other","voice":"local","input":"test"}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400


@pytest.mark.parametrize("reason", ["disconnect", "deadline", "task_cancel"])
def test_cancellation_keeps_input_until_service_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    import asyncio
    import time

    from starlette.requests import Request

    from voz.interfaces.api import openai_compat as api

    async def run() -> None:
        entered = threading.Event()
        source = tmp_path / "input.wav"
        source.write_bytes(b"synthetic")

        async def receive() -> Message:
            if reason == "disconnect" and entered.is_set():
                return {"type": "http.disconnect"}
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request({"type": "http"}, receive)

        def service(cancelled: Callable[[], bool]) -> str:
            entered.set()
            limit = time.monotonic() + 2
            while not cancelled() and time.monotonic() < limit:
                time.sleep(0.002)
            assert cancelled()
            assert source.exists()
            return "done"

        if reason == "deadline":
            monkeypatch.setattr(api, "DEADLINE_SECONDS", 0.03)
        task = asyncio.create_task(api.invoke(request, service))
        if reason == "task_cancel":
            while not entered.is_set():
                await asyncio.sleep(0.001)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(CompatibleAudioError) as error:
                await task
            assert error.value.code == (
                "client_disconnected" if reason == "disconnect" else "request_timeout"
            )

    asyncio.run(run())


def test_completed_operation_stops_monitor_when_disconnect_poll_swallows_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from starlette.requests import Request

    from voz.interfaces.api import openai_compat as api

    async def run() -> None:
        polling = threading.Event()
        swallowed = False

        async def is_disconnected() -> bool:
            nonlocal swallowed
            if not polling.is_set():
                polling.set()
                try:
                    await asyncio.Future[None]()
                except asyncio.CancelledError:
                    swallowed = True
            return False

        request = Request({"type": "http"})
        monkeypatch.setattr(request, "is_disconnected", is_disconnected)

        def service(_cancelled: Callable[[], bool]) -> str:
            assert polling.wait(1)
            return "done"

        existing_tasks = asyncio.all_tasks()
        task = asyncio.create_task(api.invoke(request, service))
        done, pending = await asyncio.wait({task}, timeout=1)
        if pending:
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        assert task in done, "Completed operation left its disconnect monitor running"
        assert task.result() == "done"
        assert swallowed
        assert asyncio.all_tasks() == existing_tasks

    asyncio.run(run())


@pytest.mark.parametrize(
    "body",
    [
        b'{"model":"local","voice":"local","input":"\\ud800"}',
        b'{"model":"local","voice":"local","input":"text","speed":' + b"9" * 500 + b"}",
    ],
)
def test_invalid_json_values_do_not_become_server_errors(
    setup: tuple[httpx.Client, FakeService, Path], body: bytes
) -> None:
    client, service, _ = setup
    assert (
        client.post(
            "/v1/audio/speech",
            content=body,
            headers={"content-type": "application/json"},
        ).status_code
        == 400
    )
    assert not service.audio.closed


def test_stream_handle_closed_on_send_failure() -> None:
    import asyncio

    from starlette.requests import ClientDisconnect
    from starlette.types import Scope

    from voz.interfaces.api.openai_compat import ClosingAudioResponse

    audio = io.BytesIO(b"RIFFsyntheticWAVE")

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body":
            raise OSError("synthetic disconnect")

    scope: Scope = {
        "type": "http",
        "asgi": {"spec_version": "2.4"},
        "method": "POST",
        "headers": [],
    }
    with pytest.raises(ClientDisconnect):
        asyncio.run(ClosingAudioResponse(audio)(scope, receive, send))
    assert audio.closed


@pytest.mark.parametrize("disconnect", [True, False])
def test_http_cancel_cleans_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, disconnect: bool
) -> None:
    import asyncio
    import time

    from starlette.types import Scope

    from voz.interfaces.api import openai_compat as api

    entered = threading.Event()

    class CancelService(FakeService):
        def transcribe(
            self, request: CompatibleTranscription, *, cancelled: Callable[[], bool]
        ) -> CompatibleTranscript:
            self.sources.append(request.source)
            entered.set()
            deadline = time.monotonic() + 2
            while not cancelled() and time.monotonic() < deadline:
                time.sleep(0.001)
            assert cancelled()
            assert request.source.exists()
            return CompatibleTranscript("cancelled", "es", 0, ())

    service = CancelService()
    app = FastAPI()
    cache = tmp_path / "cache"
    app.include_router(api.create_openai_compat_router(service, cache_root=cache))
    if not disconnect:
        monkeypatch.setattr(api, "DEADLINE_SECONDS", 0.04)

    async def run() -> list[Message]:
        read = False
        sent: list[Message] = []

        async def receive() -> Message:
            nonlocal read
            if not read:
                read = True
                return {
                    "type": "http.request",
                    "body": raw_multipart(
                        [(MODEL_HEADER, b"local"), (FILE_HEADER, b"synthetic")]
                    ),
                    "more_body": False,
                }
            if disconnect and entered.is_set():
                return {"type": "http.disconnect"}
            await asyncio.sleep(0.001)
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: Message) -> None:
            sent.append(message)

        scope: Scope = {
            "type": "http",
            "asgi": {"spec_version": "2.4"},
            "method": "POST",
            "path": "/v1/audio/transcriptions",
            "query_string": b"",
            "headers": [(b"content-type", b"multipart/form-data; boundary=boundary")],
            "server": ("test", 80),
            "client": ("test", 1),
            "scheme": "http",
        }
        await app(scope, receive, send)
        return sent

    sent = asyncio.run(run())
    assert sent[0]["status"] == (499 if disconnect else 408)
    assert service.sources and not service.sources[0].exists()
    assert list(cache.iterdir()) == []


@pytest.mark.parametrize(
    "content_type",
    [
        "multipart/form-data; boundary=boundary; boundary=other",
        "multipart/form-data; boundary=boundary; boundary=boundary",
    ],
)
def test_duplicate_boundary_parameters_rejected(
    setup: tuple[httpx.Client, FakeService, Path], content_type: str
) -> None:
    client, service, _ = setup
    response = client.post(
        "/v1/audio/transcriptions",
        content=raw_multipart([(MODEL_HEADER, b"local"), (FILE_HEADER, b"synthetic")]),
        headers={"content-type": content_type},
    )
    assert response.status_code == 400
    assert not service.sources


def test_reception_timeout_without_service_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    from starlette.requests import Request

    from voz.interfaces.api import openai_compat as api

    monkeypatch.setattr(api, "DEADLINE_SECONDS", 0.01)

    async def receive() -> Message:
        await asyncio.sleep(1)
        return {"type": "http.request", "body": b"", "more_body": False}

    async def run() -> None:
        with pytest.raises(CompatibleAudioError) as error:
            await api.body_bytes(Request({"type": "http"}, receive))
        assert error.value.status == 408

    asyncio.run(run())


def test_parser_and_service_run_off_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    from voz.interfaces.api import openai_compat as api

    original = api.multipart
    loop_thread = threading.get_ident()

    def parser(body: bytes, content_type: str) -> tuple[dict[str, str], bytes, str]:
        assert threading.get_ident() != loop_thread
        return original(body, content_type)

    class ThreadService(FakeService):
        def transcribe(
            self, request: CompatibleTranscription, *, cancelled: Callable[[], bool]
        ) -> CompatibleTranscript:
            assert threading.get_ident() != loop_thread
            return super().transcribe(request, cancelled=cancelled)

    monkeypatch.setattr(api, "multipart", parser)
    app = FastAPI()
    app.include_router(
        api.create_openai_compat_router(ThreadService(), cache_root=tmp_path / "cache")
    )

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/audio/transcriptions",
                data={"model": "local"},
                files={"file": ("clip.wav", b"synthetic")},
            )
            assert response.status_code == 200

    asyncio.run(run())


@pytest.mark.parametrize("filename", ["grabación.wav", "録音.wav", "é" * 196 + ".wav"])
def test_safe_unicode_filename(
    filename: str, setup: tuple[httpx.Client, FakeService, Path]
) -> None:
    client, service, _ = setup
    response = client.post(
        "/v1/audio/transcriptions",
        data={"model": "local"},
        files={"file": (filename, b"synthetic", "audio/wav")},
    )
    assert response.status_code == 200
    assert service.sources[0].suffix == ".wav"
    assert "grabación" not in service.sources[0].name
    assert not service.sources[0].exists()


@pytest.mark.parametrize(
    "filename",
    [
        "grabación\x00.wav",
        "grabación\x7f.wav",
        "grabación\u202e.wav",
        "grabación\u2066.wav",
        "grabación\u200b.wav",
        "grabación:voz.wav",
        "grabación/voz.wav",
        "grabación\\voz.wav",
        "é" * 197 + ".wav",
    ],
)
def test_unsafe_unicode_filename_rejected(
    setup: tuple[httpx.Client, FakeService, Path], filename: str
) -> None:
    client, service, _ = setup
    response = client.post(
        "/v1/audio/transcriptions",
        content=raw_multipart(
            [
                (MODEL_HEADER, b"local"),
                (
                    FILE_HEADER.replace("clip.wav", filename.replace("\\", "\\\\")),
                    b"synthetic",
                ),
            ]
        ),
        headers={"content-type": "multipart/form-data; boundary=boundary"},
    )
    assert response.status_code == 400
    assert not service.sources
    assert "grabación" not in response.text
