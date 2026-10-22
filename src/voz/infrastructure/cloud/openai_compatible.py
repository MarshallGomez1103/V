"""OpenAI-compatible servers as STT and TTS engines (V4-04, ADR-0010 section 5).

Two engine ids split by locality, so the registry and the UI always know
whether a request leaves the machine: ``openai-compatible`` serves only
loopback endpoints and ``openai-compatible-cloud`` only the others, which are
saved with recorded consent. Model ids are ``<endpoint id>/<server model>``
and every call re-reads the endpoint from the store: an edit or delete applies
to the next request, and a model whose endpoint moved to another locality is
refused instead of silently changing where data goes.

Requests always go through the abortable ``http.client`` path of the
transport: no redirects are followed (a loopback server cannot bounce the key
or the audio elsewhere) and cancellation shuts the socket down.
"""

from __future__ import annotations

import dataclasses
import json
import struct
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import BinaryIO, Final, cast

from voz.application.ports.compatible_endpoints import (
    CompatibleEndpoint,
    CompatibleEndpointStore,
    ConnectionCheck,
    EndpointError,
)
from voz.application.ports.provider_secrets import ProviderSecretsPort, SecretsError
from voz.application.ports.speech_synthesis import (
    PcmAudio,
    PcmSampleFormat,
    SynthesisCancellationToken,
    SynthesisError,
    SynthesisFailureCode,
    SynthesisLocality,
    SynthesisProgressCallback,
    SynthesisProviderInfo,
    SynthesisRequirements,
)
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
    TranscriptionResult,
)
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
    RuntimeAvailability,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.voice import Voice
from voz.infrastructure.cloud.http_body import MAX_AUDIO_BYTES
from voz.infrastructure.cloud.openai_limits import OpenAIModelSpec
from voz.infrastructure.cloud.openai_transcription import OpenAITranscriptionProvider
from voz.infrastructure.cloud.openai_transport import (
    HttpRequest,
    HttpResponse,
    Transport,
    TransportError,
)

LOCAL_PROVIDER_ID: Final = "openai-compatible"
CLOUD_PROVIDER_ID: Final = "openai-compatible-cloud"
PROVIDER_IDS: Final = (LOCAL_PROVIDER_ID, CLOUD_PROVIDER_ID)
LABEL: Final = "OpenAI-compatible server"
MAX_TTS_CHUNK_CHARS: Final = 4000
"""OpenAI documents 4096 input characters for ``/audio/speech``; kept below."""
MAX_STT_UPLOAD_BYTES: Final = 25_000_000
"""OpenAI's documented limit, assumed for unknown servers (conservative)."""
MAX_SPEECH_BYTES: Final = MAX_AUDIO_BYTES
"""Most audio accepted back for one chunk; more is refused, not truncated."""
PCM_SAMPLE_RATE: Final = 24_000
"""OpenAI's ``pcm`` format: 24 kHz, 16-bit little-endian mono."""
PROBE_TIMEOUT_S: Final = 5.0
_STT_CAPABILITIES: Final = frozenset(
    {ModelCapability.TRANSCRIPTION, ModelCapability.LANGUAGE_DETECTION}
)


def provider_id_for(endpoint: CompatibleEndpoint) -> str:
    return CLOUD_PROVIDER_ID if endpoint.cloud else LOCAL_PROVIDER_ID


def model_key(endpoint: CompatibleEndpoint, model: str) -> str:
    return f"{endpoint.id}/{model}"


def _descriptor(
    endpoint: CompatibleEndpoint, model: str, capabilities: frozenset[ModelCapability]
) -> ModelDescriptor:
    return ModelDescriptor(
        provider_id=provider_id_for(endpoint),
        model_id=model_key(endpoint, model),
        display_name=f"{endpoint.name} · {model}"[:128].strip(),
        capabilities=capabilities,
    )


def _listed(store: CompatibleEndpointStore) -> tuple[CompatibleEndpoint, ...]:
    try:
        return store.list()
    except EndpointError:
        return ()  # an unusable file lists nothing; the settings screen says why


def _resolve(
    store: CompatibleEndpointStore, provider_id: str, model_id: str, *, tts: bool
) -> tuple[CompatibleEndpoint, str] | None:
    endpoint_id, _, model = model_id.partition("/")
    try:
        endpoint = store.get(endpoint_id)
    except EndpointError:
        return None
    if endpoint is None or provider_id_for(endpoint) != provider_id:
        return None
    if model not in (endpoint.tts_models if tts else endpoint.stt_models):
        return None
    if endpoint.cloud and not endpoint.cloud_consent:  # defensive: never saved so
        return None
    return endpoint, model


class CompatibleModels:
    """Live catalog of the declared models with one capability."""

    def __init__(
        self, store: CompatibleEndpointStore, capability: ModelCapability
    ) -> None:
        self._store = store
        self._tts = capability is ModelCapability.SYNTHESIS
        self._capabilities = frozenset({capability}) if self._tts else _STT_CAPABILITIES

    def list_models(self) -> tuple[ModelRegistration, ...]:
        return tuple(
            ModelRegistration(
                _descriptor(endpoint, model, self._capabilities),
                InstallationStatus.REGISTERED,
                files_available=True,
                cloud=endpoint.cloud,
                provider_label=endpoint.name if endpoint.cloud else None,
                remote=True,
            )
            for endpoint in _listed(self._store)
            for model in (endpoint.tts_models if self._tts else endpoint.stt_models)
        )


class CompatibleRuntimeProbe:
    """Always available: there is nothing to install; the server may be down."""

    def probe(self, provider_id: str) -> RuntimeAvailability:
        if provider_id not in PROVIDER_IDS:
            return RuntimeAvailability(False)
        return RuntimeAvailability(True, capabilities=_STT_CAPABILITIES)


def _with_abort(transport: Transport, abort: Callable[[], bool]) -> Transport:
    def send(request: HttpRequest) -> HttpResponse:
        return transport(dataclasses.replace(request, abort=abort))

    return send


def _never() -> bool:
    return False


class CompatibleTranscriptionProvider:
    """``POST {base_url}/audio/transcriptions`` through the OpenAI adapter."""

    def __init__(
        self,
        *,
        store: CompatibleEndpointStore,
        secrets: ProviderSecretsPort,
        transport: Transport,
        cloud: bool,
        **options: float,
    ) -> None:
        self.provider_id = CLOUD_PROVIDER_ID if cloud else LOCAL_PROVIDER_ID
        self._store = store
        self._secrets = secrets
        self._transport = transport
        self._options = options  # retries/timeouts, forwarded (tests shorten them)

    def __repr__(self) -> str:
        return f"CompatibleTranscriptionProvider({self.provider_id!r})"

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        resolved = _resolve(
            self._store, self.provider_id, options.model.model_id, tts=False
        )
        if resolved is None:
            raise TranscriptionError(
                TranscriptionFailureCode.MODEL_NOT_INSTALLED,
                "The OpenAI-compatible server or model is no longer configured.",
            )
        endpoint, model = resolved
        spec = OpenAIModelSpec(
            model, model, "verbose_json", MAX_STT_UPLOAD_BYTES, Decimal(0)
        )
        engine = OpenAITranscriptionProvider(
            secrets=self._secrets,
            transport=_with_abort(
                self._transport,
                _never if cancellation is None else cancellation.is_cancelled,
            ),
            endpoint=f"{endpoint.base_url}/audio/transcriptions",
            provider_id=self.provider_id,
            spec_for=lambda model_id: (
                spec if model_id == options.model.model_id else None
            ),
            secret_id=endpoint.secret_id,
            key_required=False,
            label=LABEL,
            **self._options,  # type: ignore[arg-type]
        )
        try:
            return engine.transcribe(
                audio=audio, options=options, cancellation=cancellation
            )
        except TranscriptionError:
            if cancellation is not None and cancellation.is_cancelled():
                raise TranscriptionError(
                    TranscriptionFailureCode.CANCELLED, "Transcription was cancelled."
                ) from None
            raise


def _synthesis_error(
    code: SynthesisFailureCode, message: str, *, retryable: bool = False
) -> SynthesisError:
    return SynthesisError(code, message, retryable=retryable)


def _cancelled() -> SynthesisError:
    return _synthesis_error(SynthesisFailureCode.CANCELLED, "Synthesis was cancelled.")


def _failed(message: str, *, retryable: bool = False) -> SynthesisError:
    return _synthesis_error(
        SynthesisFailureCode.SYNTHESIS_FAILED, message, retryable=retryable
    )


def _header(headers: Mapping[str, str], name: str) -> str:
    return next(
        (value for key, value in headers.items() if key.lower() == name), ""
    ).lower()


def decode_speech(body: bytes, content_type: str) -> PcmAudio:
    """WAV (PCM16 or float32, first channel) or raw OpenAI ``pcm`` to PCM.

    Streaming servers often write 0 or 0xFFFFFFFF as the data size: the rest of
    the body is then the data.
    """
    if body[:4] != b"RIFF" or body[8:12] != b"WAVE":
        if "pcm" in content_type and len(body) >= 2:
            return PcmAudio(body[: len(body) // 2 * 2], PCM_SAMPLE_RATE)
        raise _failed("The server did not return WAV audio.")
    offset = 12
    fmt: tuple[int, int, int, int] | None = None
    while offset + 8 <= len(body):
        chunk, size = (
            body[offset : offset + 4],
            struct.unpack_from("<I", body, offset + 4)[0],
        )
        start = offset + 8
        if chunk == b"fmt " and start + size > len(body):
            raise _failed("The server returned an unreadable WAV file.")
        if chunk == b"fmt " and size >= 16:
            tag, channels, rate = struct.unpack_from("<HHI", body, start)
            bits = struct.unpack_from("<H", body, start + 14)[0]
            if tag == 0xFFFE and size >= 26:  # WAVE_FORMAT_EXTENSIBLE
                tag = struct.unpack_from("<H", body, start + 24)[0]
            fmt = (tag, channels, rate, bits)
        elif chunk == b"data" and fmt is not None:
            end = len(body) if size in (0, 0xFFFFFFFF) else start + size
            return _pcm(body[start:end], *fmt)
        offset = start + size + (size & 1)
    raise _failed("The server returned an unreadable WAV file.")


def _pcm(data: bytes, tag: int, channels: int, rate: int, bits: int) -> PcmAudio:
    if (tag, bits) == (1, 16):
        sample_format = PcmSampleFormat.INT16
    elif (tag, bits) == (3, 32):
        sample_format = PcmSampleFormat.FLOAT32
    else:
        raise _failed("The server returned an unsupported WAV sample format.")
    if channels < 1 or rate <= 0:
        raise _failed("The server returned an unreadable WAV file.")
    width = sample_format.width
    frame = width * channels
    data = data[: len(data) // frame * frame]
    if channels > 1:  # ponytail: keep the first channel instead of mixing
        data = b"".join(data[i : i + width] for i in range(0, len(data), frame))
    if not data:
        raise _failed("The server returned empty audio.")
    return PcmAudio(data, rate, sample_format)


class CompatibleSpeechProvider:
    """``POST {base_url}/audio/speech`` asking for ``wav``; one chunk per call."""

    def __init__(
        self,
        *,
        store: CompatibleEndpointStore,
        secrets: ProviderSecretsPort,
        transport: Transport,
        cloud: bool,
        timeout_s: float = 300.0,
    ) -> None:
        self._info = SynthesisProviderInfo(
            CLOUD_PROVIDER_ID if cloud else LOCAL_PROVIDER_ID,
            f"{LABEL} (cloud)" if cloud else LABEL,
            locality=SynthesisLocality.CLOUD if cloud else SynthesisLocality.LOCAL,
            max_chunk_chars=MAX_TTS_CHUNK_CHARS,
        )
        self._store = store
        self._secrets = secrets
        self._transport = transport
        self._timeout_s = timeout_s

    def __repr__(self) -> str:
        return f"CompatibleSpeechProvider({self._info.provider_id!r})"

    def describe(self) -> SynthesisProviderInfo:
        return self._info

    def _endpoint(self, model: ModelDescriptor) -> tuple[CompatibleEndpoint, str]:
        resolved = (
            _resolve(self._store, self._info.provider_id, model.model_id, tts=True)
            if model.provider_id == self._info.provider_id
            else None
        )
        if resolved is None:
            raise _synthesis_error(
                SynthesisFailureCode.MODEL_NOT_INSTALLED,
                "The OpenAI-compatible server or model is no longer configured.",
            )
        return resolved

    def voices(self, model: ModelDescriptor) -> tuple[Voice, ...]:
        endpoint, _ = self._endpoint(model)
        return tuple(Voice(voice, voice) for voice in endpoint.tts_voices)

    def languages(self, model: ModelDescriptor) -> tuple[str, ...]:
        self._endpoint(model)
        return ()  # the server does not declare them

    def requirements(self, model: ModelDescriptor) -> SynthesisRequirements:
        self._endpoint(model)
        return SynthesisRequirements(runtime_ready=True)

    def synthesize(
        self,
        chunk_text: str,
        *,
        model: ModelDescriptor,
        voice_id: str,
        speed: float = 1.0,
        cancellation: SynthesisCancellationToken | None = None,
        on_progress: SynthesisProgressCallback | None = None,
    ) -> PcmAudio:
        cancelled = _never if cancellation is None else cancellation.is_cancelled
        if cancelled():
            raise _cancelled()
        endpoint, server_model = self._endpoint(model)
        if voice_id not in endpoint.tts_voices:
            raise _synthesis_error(
                SynthesisFailureCode.VOICE_NOT_FOUND,
                "The selected voice is not declared for this server.",
            )
        if len(chunk_text) > self._info.max_chunk_chars:
            raise _synthesis_error(
                SynthesisFailureCode.TEXT_TOO_LONG, "The text chunk is too long."
            )
        headers = {"Content-Type": "application/json", "Accept": "audio/wav"}
        try:
            key = self._secrets.get(endpoint.secret_id)
        except SecretsError:
            raise _failed("The API key storage is unusable.") from None
        if key is not None:
            headers["Authorization"] = f"Bearer {key}"
        body = json.dumps(
            {
                "model": server_model,
                "input": chunk_text,
                "voice": voice_id,
                "response_format": "wav",
                "speed": speed,
            }
        ).encode()
        request = HttpRequest(
            f"{endpoint.base_url}/audio/speech",
            headers,
            body,
            self._timeout_s,
            abort=cancelled,
            max_response_bytes=MAX_SPEECH_BYTES,
        )
        try:
            reply = self._transport(request)
        except TransportError as error:
            if error.aborted or cancelled():
                raise _cancelled() from None
            if error.oversized:
                raise _failed(f"The {LABEL} returned too much audio.") from None
            raise _synthesis_error(
                SynthesisFailureCode.RUNTIME_UNAVAILABLE,
                f"The {LABEL} did not answer in time."
                if error.timeout
                else f"The {LABEL} could not be reached.",
                retryable=True,
            ) from None
        if cancelled():
            raise _cancelled()
        if reply.status != 200:
            raise _http_failure(reply.status)
        audio = decode_speech(reply.body, _header(reply.headers, "content-type"))
        if on_progress is not None:
            on_progress(1.0)
        return audio

    def close(self) -> None:
        """Nothing is held between calls."""


def _http_failure(status: int) -> SynthesisError:
    if status in (401, 403):
        return _failed(f"The {LABEL} rejected the API key.")
    if status == 429 or status >= 500:
        return _failed(f"The {LABEL} is busy or failing ({status}).", retryable=True)
    return _failed(f"The {LABEL} rejected the request ({status}).")


class HttpConnectionTester:
    """``GET {base_url}/models`` with a short timeout; reports, never raises."""

    def __init__(self, transport: Transport, timeout_s: float = PROBE_TIMEOUT_S):
        self._transport = transport
        self._timeout_s = timeout_s

    def check(self, endpoint: CompatibleEndpoint, key: str | None) -> ConnectionCheck:
        headers = {"Accept": "application/json"}
        if key is not None:
            headers["Authorization"] = f"Bearer {key}"
        request = HttpRequest(
            f"{endpoint.base_url}/models",
            headers,
            b"",
            self._timeout_s,
            method="GET",
            abort=_never,
        )
        try:
            reply = self._transport(request)
        except TransportError as error:
            return ConnectionCheck(
                False,
                code="endpoint_timeout" if error.timeout else "endpoint_unreachable",
            )
        if reply.status in (401, 403):
            return ConnectionCheck(True, reply.status, code="endpoint_auth_rejected")
        if reply.status == 404:  # reachable, but it does not list models
            return ConnectionCheck(True, 404, code="endpoint_models_unlisted")
        if reply.status != 200:
            return ConnectionCheck(True, reply.status, code="endpoint_http_error")
        return ConnectionCheck(True, 200, _model_ids(reply.body))


def _model_ids(raw: bytes) -> tuple[str, ...]:
    try:
        document = cast(object, json.loads(raw))
    except (UnicodeDecodeError, ValueError):
        return ()
    data = (
        cast(dict[str, object], document).get("data")
        if isinstance(document, dict)
        else None
    )
    if not isinstance(data, list):
        return ()
    found: list[str] = []
    for item in cast(list[object], data):
        if isinstance(item, dict):
            value = cast(dict[str, object], item).get("id")
            if isinstance(value, str) and value.strip() and len(value) <= 255:
                found.append(value)
    return tuple(found[:200])


__all__ = [
    "CLOUD_PROVIDER_ID",
    "LOCAL_PROVIDER_ID",
    "MAX_TTS_CHUNK_CHARS",
    "PROVIDER_IDS",
    "CompatibleModels",
    "CompatibleRuntimeProbe",
    "CompatibleSpeechProvider",
    "CompatibleTranscriptionProvider",
    "HttpConnectionTester",
    "decode_speech",
    "model_key",
    "provider_id_for",
]
