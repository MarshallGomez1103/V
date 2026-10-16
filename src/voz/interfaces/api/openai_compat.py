"""Bounded local audio HTTP compatibility, without multipart dependencies."""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import tempfile
import threading
import time
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from email import policy
from email.errors import UndecodableBytesDefect
from email.parser import BytesParser
from pathlib import Path
from typing import BinaryIO, cast

from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool
from starlette.background import BackgroundTask
from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse, StreamingResponse
from starlette.types import Receive, Scope, Send

from voz.application.ports.compatible_audio import (
    CompatibleAudioError,
    CompatibleAudioService,
    CompatibleSpeech,
    CompatibleTranscription,
)
from voz.domain.filename_safety import has_unsafe_filename_character

BODY_LIMIT = 26 * 1024**2
FILE_LIMIT = 25 * 1024**2
TEXT_LIMIT = 8 * 1024
DEADLINE_SECONDS = 300.0
SUFFIXES = {
    ".wav",
    ".mp3",
    ".m4a",
    ".ogg",
    ".flac",
    ".webm",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".oga",
}


def invalid(param: str | None = None) -> CompatibleAudioError:
    return CompatibleAudioError(
        "invalid_request", "Invalid or unsupported request parameter.", param=param
    )


def error_response(error: CompatibleAudioError) -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "message": error.message,
                "type": "server_error"
                if error.status >= 500
                else "invalid_request_error",
                "param": error.param,
                "code": error.code,
            }
        },
        status_code=error.status,
    )


async def body_bytes(request: Request) -> bytes:
    body = bytearray()
    try:
        async with asyncio.timeout(DEADLINE_SECONDS):
            async for chunk in request.stream():
                if len(body) + len(chunk) > BODY_LIMIT:
                    raise CompatibleAudioError(
                        "request_too_large", "Request body exceeds the size limit.", 413
                    )
                body.extend(chunk)
    except TimeoutError:
        raise CompatibleAudioError(
            "request_timeout", "Request deadline exceeded.", 408
        ) from None
    return bytes(body)


def multipart(body: bytes, content_type: str) -> tuple[dict[str, str], bytes, str]:
    if len(content_type) > 1024 or "\r" in content_type or "\n" in content_type:
        raise invalid()
    try:
        message = BytesParser(policy=policy.default).parsebytes(
            b"Content-Type: "
            + content_type.encode("ascii")
            + b"\r\nMIME-Version: 1.0\r\n\r\n"
            + body
        )
    except (UnicodeError, ValueError, RecursionError):
        raise invalid() from None
    if (
        message.get_content_type() != "multipart/form-data"
        or not message.is_multipart()
        or message.defects
        or any(getattr(value, "defects", ()) for value in message.values())
    ):
        raise invalid()
    boundary = message.get_boundary()
    if boundary is None or not re.fullmatch(r"[\x21-\x7e]{1,70}", boundary):
        raise invalid()
    parts = list(message.iter_parts())
    if len(parts) > 16:
        raise invalid()
    fields: dict[str, str] = {}
    audio: bytes | None = None
    suffix = ""
    for part in parts:
        if part.is_multipart() or part.defects:
            raise invalid()
        for header, value in part.items():
            if any(
                header.lower() != "content-disposition"
                or not isinstance(defect, UndecodableBytesDefect)
                for defect in getattr(value, "defects", ())
            ):
                raise invalid()
        # MIME flags raw UTF-8 filenames as non-ASCII; validate their bytes.
        try:
            for _, raw in part.raw_items():
                raw.encode("utf-8", errors="surrogateescape").decode("utf-8")
        except UnicodeError:
            raise invalid() from None
        for header in part:
            if len(part.get_all(header, [])) != 1:
                raise invalid()
        if (
            part.get("Content-Transfer-Encoding") is not None
            or part.get_content_disposition() != "form-data"
        ):
            raise invalid()
        params = part.get_params(header="content-disposition", unquote=True) or []
        names = [key for key, _ in params]
        if len(names) != len(set(names)):
            raise invalid()
        name = part.get_param("name", header="content-disposition")
        if (
            not isinstance(name, str)
            or name in fields
            or (name == "file" and audio is not None)
        ):
            raise invalid()
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            raise invalid()
        filename = part.get_filename()
        if name == "file":
            if (
                not filename
                or len(filename) > 200
                or any(character in filename for character in "/\\:")
                or has_unsafe_filename_character(filename)
                or ".." in filename
            ):
                raise invalid("file")
            suffix = Path(filename).suffix.lower()
            if suffix not in SUFFIXES:
                raise invalid("file")
            if not payload or len(payload) > FILE_LIMIT:
                raise CompatibleAudioError(
                    "file_too_large",
                    "File is empty or exceeds the size limit.",
                    413,
                    "file",
                )
            audio = payload
        else:
            if (
                name not in {"model", "language", "prompt", "response_format"}
                or filename is not None
                or len(payload) > TEXT_LIMIT
            ):
                raise invalid()
            try:
                fields[name] = payload.decode("utf-8", errors="strict")
            except UnicodeError:
                raise invalid() from None
    if audio is None or not fields.get("model"):
        raise invalid()
    if fields.get("response_format", "json") not in {"json", "text", "verbose_json"}:
        raise invalid("response_format")
    return fields, audio, suffix


def speech_request(body: bytes) -> CompatibleSpeech:
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        values: dict[str, object] = {}
        for key, value in items:
            if key in values:
                raise invalid()
            values[key] = value
        return values

    try:
        parsed: object = json.loads(body, object_pairs_hook=pairs)
    except (ValueError, UnicodeError, RecursionError):
        raise invalid() from None
    if not isinstance(parsed, dict):
        raise invalid()
    data = cast(dict[str, object], parsed)
    if set(data) - {
        "model",
        "input",
        "voice",
        "speed",
        "response_format",
    }:
        raise invalid()
    strings: dict[str, str] = {}
    for key in ("model", "input", "voice"):
        value = data.get(key)
        if not isinstance(value, str) or not value:
            raise invalid(key)
        try:
            size = len(value.encode("utf-8"))
        except UnicodeError:
            raise invalid(key) from None
        if size > TEXT_LIMIT:
            raise invalid(key)
        strings[key] = value
    if data.get("response_format", "wav") != "wav":
        raise invalid("response_format")
    speed = data.get("speed", 1.0)
    if (
        isinstance(speed, bool)
        or not isinstance(speed, (int, float))
        or not 0.25 <= speed <= 4
        or not math.isfinite(speed)
    ):
        raise invalid("speed")
    return CompatibleSpeech(
        strings["model"], strings["input"], strings["voice"], float(speed)
    )


async def invoke[T](
    request: Request, operation: Callable[[Callable[[], bool]], T]
) -> T:
    cancelled = threading.Event()
    reason: str | None = None
    deadline = time.monotonic() + DEADLINE_SECONDS

    async def watch() -> None:
        nonlocal reason
        while True:
            if time.monotonic() >= deadline:
                reason = "request_timeout"
            elif await request.is_disconnected():
                reason = "client_disconnected"
            if reason:
                cancelled.set()
                return
            await asyncio.sleep(0.02)

    watcher = asyncio.create_task(watch())
    worker = asyncio.create_task(run_in_threadpool(operation, cancelled.is_set))
    try:
        result = await asyncio.shield(worker)
        if reason:
            if hasattr(result, "close"):
                await run_in_threadpool(result.close)
            raise CompatibleAudioError(
                reason,
                "Request cancelled.",
                408 if reason == "request_timeout" else 499,
            )
        return result
    except asyncio.CancelledError:
        cancelled.set()
        # Keep uploaded input alive until the cooperative service releases it.
        with suppress(Exception):
            late_result = await asyncio.shield(worker)
            if hasattr(late_result, "close"):
                await run_in_threadpool(cast(BinaryIO, late_result).close)
        raise
    finally:
        cancelled.set()
        watcher.cancel()
        with suppress(asyncio.CancelledError):
            await watcher


class ClosingAudioResponse(StreamingResponse):
    def __init__(self, audio: BinaryIO) -> None:
        self.audio = audio

        async def chunks() -> AsyncIterator[bytes]:
            try:
                while chunk := await run_in_threadpool(audio.read, 64 * 1024):
                    yield chunk
            finally:
                await run_in_threadpool(audio.close)

        super().__init__(
            chunks(), media_type="audio/wav", background=BackgroundTask(audio.close)
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await run_in_threadpool(self.audio.close)


def create_openai_compat_router(
    service: CompatibleAudioService, *, cache_root: Path
) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["OpenAI compatible audio"])

    async def models(request: Request) -> Response:
        try:
            if request.query_params:
                raise invalid()
            entries = await run_in_threadpool(service.models)
            return JSONResponse(
                {
                    "object": "list",
                    "data": [
                        {
                            "id": m.id,
                            "object": "model",
                            "created": 0,
                            "owned_by": m.owned_by,
                            "capabilities": list(m.capabilities),
                        }
                        for m in entries
                    ],
                }
            )
        except CompatibleAudioError as error:
            return error_response(error)
        except Exception:
            return error_response(
                CompatibleAudioError(
                    "internal_error", "Local audio operation failed.", 500
                )
            )

    async def transcribe(request: Request) -> Response:
        try:
            if request.query_params:
                raise invalid()
            body = await body_bytes(request)
            fields, audio, suffix = await run_in_threadpool(
                multipart, body, request.headers.get("content-type", "")
            )
            cache_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.TemporaryDirectory(
                prefix="compatible-", dir=cache_root
            ) as directory:
                descriptor, name = tempfile.mkstemp(suffix=suffix, dir=directory)
                with os.fdopen(descriptor, "wb") as handle:
                    await run_in_threadpool(handle.write, audio)
                command = CompatibleTranscription(
                    Path(name),
                    fields["model"],
                    fields.get("language"),
                    fields.get("prompt"),
                )
                result = await invoke(
                    request,
                    lambda cancelled: service.transcribe(command, cancelled=cancelled),
                )
            format = fields.get("response_format", "json")
            if format == "text":
                return Response(result.text, media_type="text/plain")
            if format == "json":
                return JSONResponse({"text": result.text})
            return JSONResponse(
                {
                    "task": "transcribe",
                    "language": result.language,
                    "duration": result.duration_seconds,
                    "text": result.text,
                    "segments": [
                        {
                            "id": index,
                            "start": segment.start_ms / 1000,
                            "end": segment.end_ms / 1000,
                            "text": segment.text,
                        }
                        for index, segment in enumerate(result.segments)
                    ],
                }
            )
        except CompatibleAudioError as error:
            return error_response(error)
        except ClientDisconnect:
            return error_response(
                CompatibleAudioError("client_disconnected", "Request cancelled.", 499)
            )
        except Exception:
            return error_response(
                CompatibleAudioError(
                    "internal_error", "Local audio operation failed.", 500
                )
            )

    async def speech(request: Request) -> Response:
        try:
            if (
                request.query_params
                or request.headers.get("content-type", "").split(";", 1)[0].strip()
                != "application/json"
            ):
                raise invalid()
            command = await run_in_threadpool(speech_request, await body_bytes(request))
            audio = await invoke(
                request, lambda cancelled: service.speech(command, cancelled=cancelled)
            )
            return ClosingAudioResponse(audio)
        except CompatibleAudioError as error:
            return error_response(error)
        except ClientDisconnect:
            return error_response(
                CompatibleAudioError("client_disconnected", "Request cancelled.", 499)
            )
        except Exception:
            return error_response(
                CompatibleAudioError(
                    "internal_error", "Local audio operation failed.", 500
                )
            )

    router.add_api_route("/models", models, methods=["GET"])
    router.add_api_route("/audio/transcriptions", transcribe, methods=["POST"])
    router.add_api_route("/audio/speech", speech, methods=["POST"])
    return router
