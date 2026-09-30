"""ElevenLabs Scribe transcription adapter (optional cloud provider).

The audio leaves the machine only when a job explicitly selects this provider and
a key is configured; nothing here activates itself or falls back to it. Provider
request/response types stay in this adapter and its sibling modules. The HTTP
transport is injected so tests never reach the network.

Per-project key terms are passed to the constructor by whoever composes the
adapter; the project glossary model itself is S13.01 and is not part of this
adapter. The API key is fetched per call and is never stored, logged or echoed.
"""

from __future__ import annotations

import io
import json
import logging
import uuid
import wave
from collections.abc import Sequence
from typing import BinaryIO, Final

from voz.application.ports.provider_secrets import ProviderSecretsPort, SecretsError
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionClip,
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
    TranscriptionResult,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.infrastructure.cloud.elevenlabs_mapping import (
    InvalidScribeResponse,
    map_scribe_response,
)
from voz.infrastructure.cloud.elevenlabs_transport import (
    HttpRequest,
    MultipartBody,
    Transport,
    TransportError,
    UploadProgress,
    http_transport,
    multipart_parts,
)

PROVIDER_ID: Final = "elevenlabs"
SCRIBE_URL: Final = "https://api.elevenlabs.io/v1/speech-to-text"
# ponytail: dated limits from ElevenLabs public docs as remembered on 2026-09-30
# (file under 3 GB); NOT verified live. Raise or lower via ``max_upload_bytes``.
LIMITS_DATE: Final = "2026-09-30"
MAX_UPLOAD_BYTES: Final = 3 * 1024**3
MAX_KEYTERMS: Final = 100
MAX_KEYTERM_LENGTH: Final = 50
_TIMEOUT_BASE_S: Final = 300.0
_TIMEOUT_MAX_S: Final = 3600.0

_logger = logging.getLogger(__name__)


def elevenlabs_scribe_descriptor() -> ModelDescriptor:
    """Canonical identity of the Scribe v1 model (cloud: no CPU/GPU capability)."""
    return ModelDescriptor(
        provider_id=PROVIDER_ID,
        model_id="scribe_v1",
        display_name="ElevenLabs Scribe v1",
        capabilities=frozenset(
            {
                ModelCapability.TRANSCRIPTION,
                ModelCapability.WORD_TIMESTAMPS,
                ModelCapability.DIARIZATION,
                ModelCapability.LANGUAGE_DETECTION,
            }
        ),
    )


def normalize_keyterms(terms: Sequence[str]) -> tuple[str, ...]:
    """Trim, drop blanks, dedupe (order kept) and enforce the request limits."""
    clean: dict[str, None] = {}
    for term in terms:
        stripped = term.strip()
        if not stripped:
            continue
        if len(stripped) > MAX_KEYTERM_LENGTH or not stripped.isprintable():
            raise ValueError("keyterms must be short printable strings")
        clean.setdefault(stripped)
    if len(clean) > MAX_KEYTERMS:
        raise ValueError(f"at most {MAX_KEYTERMS} keyterms are allowed")
    return tuple(clean)


def _failure(message: str, *, retryable: bool = False) -> TranscriptionError:
    return TranscriptionError(
        TranscriptionFailureCode.PROVIDER_FAILED, message, retryable=retryable
    )


def _invalid_audio() -> TranscriptionError:
    return TranscriptionError(
        TranscriptionFailureCode.INVALID_AUDIO, "The selected audio is invalid."
    )


def _raise_if_cancelled(cancellation: TranscriptionCancellationToken | None) -> None:
    if cancellation is not None and cancellation.is_cancelled():
        raise TranscriptionError(
            TranscriptionFailureCode.CANCELLED, "Transcription was cancelled."
        )


def _clip_wav(audio: BinaryIO, clip: TranscriptionClip) -> tuple[BinaryIO, int, float]:
    """Return a WAV holding only ``clip`` plus its byte length and duration."""
    with wave.open(audio, "rb") as source:
        rate = source.getframerate()
        first = min(source.getnframes(), clip.start_ms * rate // 1000)
        last = min(source.getnframes(), clip.end_ms * rate // 1000)
        source.setpos(first)
        frames = source.readframes(last - first)
        out = io.BytesIO()
        with wave.open(out, "wb") as target:
            target.setparams(source.getparams())
            target.writeframes(frames)
    return io.BytesIO(out.getvalue()), len(out.getvalue()), (last - first) / rate


def _prepare_audio(
    audio: BinaryIO, clip: TranscriptionClip | None
) -> tuple[BinaryIO, int, float]:
    """Validate the WAV locally; return stream, byte length and seconds."""
    try:
        if not audio.seekable():
            audio = io.BytesIO(audio.read())
        audio.seek(0, io.SEEK_END)
        size = audio.tell()
        audio.seek(0)
        if clip is not None:
            return _clip_wav(audio, clip)
        with wave.open(audio, "rb") as parsed:
            seconds = parsed.getnframes() / parsed.getframerate()
        audio.seek(0)
    except (EOFError, wave.Error, ZeroDivisionError, OSError) as error:
        raise _invalid_audio() from error
    return audio, size, seconds


class ElevenLabsScribeProvider:
    """``TranscriptionProvider`` backed by the ElevenLabs speech-to-text API."""

    provider_id = PROVIDER_ID

    def __init__(
        self,
        *,
        secrets: ProviderSecretsPort,
        transport: Transport = http_transport,
        keyterms: Sequence[str] = (),
        diarize: bool = True,
        max_upload_bytes: int = MAX_UPLOAD_BYTES,
        timeout_s: float | None = None,
        on_upload_progress: UploadProgress | None = None,
    ) -> None:
        self._secrets = secrets
        self._transport = transport
        self._keyterms = normalize_keyterms(keyterms)
        self._diarize = diarize
        self._max_upload_bytes = max_upload_bytes
        self._timeout_s = timeout_s
        self._on_upload_progress = on_upload_progress

    def __repr__(self) -> str:
        return "ElevenLabsScribeProvider()"

    def _api_key(self) -> str:
        try:
            key = self._secrets.get(PROVIDER_ID)
        except SecretsError as error:
            raise _failure("The ElevenLabs API key could not be read.") from error
        if key is None:
            raise _failure("The ElevenLabs API key is not configured.")
        return key

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        """Upload ``audio`` to Scribe and map the answer; never retries a POST."""
        _raise_if_cancelled(cancellation)
        if options.model.provider_id != PROVIDER_ID:
            raise TranscriptionError(
                TranscriptionFailureCode.MODEL_NOT_INSTALLED,
                "The selected model does not belong to ElevenLabs.",
            )
        key = self._api_key()
        stream, size, seconds = _prepare_audio(audio, options.clip)
        if size > self._max_upload_bytes:
            raise TranscriptionError(
                TranscriptionFailureCode.INVALID_AUDIO,
                "The selected audio exceeds the configured upload limit.",
            )
        fields = [
            ("model_id", options.model.model_id),
            ("diarize", "true" if self._diarize else "false"),
            ("timestamps_granularity", "word"),
            ("tag_audio_events", "false"),
        ]
        if options.language is not None:
            fields.append(("language_code", options.language.split("-")[0].lower()))
        fields.extend(("keyterms", term) for term in self._keyterms)
        boundary = f"voz-{uuid.uuid4().hex}"
        head, tail = multipart_parts(
            boundary=boundary,
            fields=fields,
            file_field="file",
            filename="audio.wav",
            content_type="audio/wav",
        )
        body = MultipartBody(
            head=head,
            audio=stream,
            audio_length=size,
            tail=tail,
            on_progress=self._on_upload_progress,
            cancellation=cancellation,
        )
        request = HttpRequest(
            url=SCRIBE_URL,
            headers={
                "xi-api-key": key,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Accept": "application/json",
            },
            body=body,
            content_length=body.length,
            timeout_s=self._timeout_s or min(_TIMEOUT_MAX_S, _TIMEOUT_BASE_S + seconds),
        )
        try:
            response = self._transport(request)
        except TransportError as error:
            raise _failure(
                "ElevenLabs did not answer in time."
                if error.timeout
                else "ElevenLabs could not be reached.",
                retryable=True,
            ) from error
        _raise_if_cancelled(cancellation)
        return self._result(response.status, response.body, options)

    @staticmethod
    def _result(
        status: int, raw: bytes, options: TranscriptionOptions
    ) -> TranscriptionResult:
        if status in {401, 403}:
            raise _failure("ElevenLabs rejected the API key.")
        if status in {413, 415}:
            raise TranscriptionError(
                TranscriptionFailureCode.INVALID_AUDIO,
                "ElevenLabs rejected the selected audio.",
            )
        if status == 429 or status >= 500:
            raise _failure("ElevenLabs is temporarily unavailable.", retryable=True)
        if status != 200:
            _logger.warning("ElevenLabs answered HTTP %d", status)
            raise _failure("ElevenLabs rejected the request.")
        offset = 0 if options.clip is None else options.clip.start_ms
        try:
            return map_scribe_response(
                json.loads(raw),
                requested_language=options.language,
                offset_ms=offset,
                with_words=options.word_timestamps,
            )
        except (ValueError, InvalidScribeResponse) as error:
            raise _failure("ElevenLabs returned an unexpected response.") from error


__all__ = [
    "LIMITS_DATE",
    "MAX_UPLOAD_BYTES",
    "PROVIDER_ID",
    "SCRIBE_URL",
    "ElevenLabsScribeProvider",
    "elevenlabs_scribe_descriptor",
    "normalize_keyterms",
]
