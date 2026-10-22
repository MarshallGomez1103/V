"""OpenAI audio transcription adapter (cloud, opt-in, never implicit).

Privacy: constructing this provider performs no I/O. The only network access is
inside ``transcribe``, through the injected ``Transport``, and only after the
user selected an ``openai`` model for that job. There is no fallback to or from
local providers. The API key is read from ``ProviderSecretsPort`` per call and
never stored, logged or included in an error message.

Limits and prices are dated constants (see ``openai_limits``); the request and
response shapes below follow the public docs and are **not verified live**.
"""

from __future__ import annotations

import json
import math
import random
import re
import time
import wave
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO, Final, cast

from voz.application.chunked_transcription import plan_audio_chunks
from voz.application.ports.provider_secrets import ProviderSecretsPort, SecretsError
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
    TranscriptionResult,
    TranscriptionSegment,
)
from voz.infrastructure.cloud._errors import invalid_audio_error
from voz.infrastructure.cloud.openai_limits import (
    PROVIDER_ID,
    OpenAIModelSpec,
    openai_spec,
)
from voz.infrastructure.cloud.openai_transport import (
    HttpRequest,
    Transport,
    TransportError,
    encode_multipart,
)

ENDPOINT: Final = "https://api.openai.com/v1/audio/transcriptions"
_HEADER_MARGIN_BYTES = 1024
_SLEEP_SLICE_S = 0.25
# ponytail: common Whisper names only; unknown names fall back to the requested tag.
_LANGUAGE_CODES = {
    "arabic": "ar", "catalan": "ca", "chinese": "zh", "czech": "cs",
    "danish": "da", "dutch": "nl", "english": "en", "finnish": "fi",
    "french": "fr", "german": "de", "greek": "el", "hebrew": "he",
    "hindi": "hi", "hungarian": "hu", "indonesian": "id", "italian": "it",
    "japanese": "ja", "korean": "ko", "norwegian": "no", "polish": "pl",
    "portuguese": "pt", "romanian": "ro", "russian": "ru", "spanish": "es",
    "swedish": "sv", "turkish": "tr", "ukrainian": "uk", "vietnamese": "vi",
}  # fmt: skip
_CODE = re.compile(r"[a-z]{2,3}", re.ASCII)


def _fail(message: str, *, retryable: bool = False) -> TranscriptionError:
    return TranscriptionError(
        TranscriptionFailureCode.PROVIDER_FAILED, message, retryable=retryable
    )


def _cancelled() -> TranscriptionError:
    return TranscriptionError(
        TranscriptionFailureCode.CANCELLED, "Transcription was cancelled."
    )


@dataclass(frozen=True, slots=True)
class _Window:
    """Audio sent in one request plus the timeline region whose text it owns."""

    process_start_ms: int
    process_end_ms: int
    owned_start_ms: int
    owned_end_ms: int


class OpenAITranscriptionProvider:
    """``whisper-1`` (verbose_json) and ``gpt-4o-transcribe-diarize`` by model id.

    The keyword-only ``provider_id``/``spec_for``/``secret_id``/``key_required``/
    ``label`` let the OpenAI-compatible engine (V4-04) reuse this adapter for
    any ``/v1/audio/transcriptions`` server; the defaults are OpenAI's.
    """

    def __init__(
        self,
        *,
        secrets: ProviderSecretsPort,
        transport: Transport,
        max_upload_bytes: int | None = None,
        overlap_ms: int = 2_000,
        max_attempts: int = 4,
        base_delay_s: float = 1.0,
        max_delay_s: float = 30.0,
        timeout_s: float = 600.0,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
        endpoint: str = ENDPOINT,
        provider_id: str = PROVIDER_ID,
        spec_for: Callable[[str], OpenAIModelSpec | None] = openai_spec,
        secret_id: str | None = None,
        key_required: bool = True,
        label: str = "OpenAI",
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._secrets = secrets
        self._transport = transport
        self._max_upload_bytes = max_upload_bytes
        self._overlap_ms = overlap_ms
        self._max_attempts = max_attempts
        self._base_delay_s = base_delay_s
        self._max_delay_s = max_delay_s
        self._timeout_s = timeout_s
        self._sleep = sleep
        self._jitter = jitter
        self._endpoint = endpoint
        self.provider_id = provider_id
        self._spec_for = spec_for
        self._secret_id = provider_id if secret_id is None else secret_id
        self._key_required = key_required
        self._label = label

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        spec = (
            self._spec_for(options.model.model_id)
            if options.model.provider_id == self.provider_id
            else None
        )
        if spec is None:
            raise TranscriptionError(
                TranscriptionFailureCode.MODEL_NOT_INSTALLED,
                f"The selected model does not belong to {self._label}.",
            )
        self._check(cancellation)
        try:
            key = self._secrets.get(self._secret_id)
        except SecretsError:
            raise _fail(f"The {self._label} API key storage is unusable.") from None
        if key is None and self._key_required:
            raise _fail(f"The {self._label} API key is not configured.")

        payload = audio.read()
        try:
            source = wave.open(BytesIO(payload), "rb")  # noqa: SIM115 - closed below
        except (EOFError, wave.Error):
            raise invalid_audio_error() from None
        with source:
            rate = source.getframerate()
            if rate <= 0:
                raise invalid_audio_error()
            total_ms = source.getnframes() * 1000 // rate
            windows = self._plan(
                total_ms,
                source.getsampwidth() * source.getnchannels(),
                rate,
                options,
                spec,
                len(payload),
            )
            whole = len(windows) == 1 and options.clip is None
            segments: list[TranscriptionSegment] = []
            language: str | None = None
            for index, window in enumerate(windows):
                self._check(cancellation)
                body = (
                    payload
                    if whole and len(payload) <= self._limit(spec)
                    else _slice(source, rate, window)
                )
                reply = self._post(body, key, spec, options, cancellation)
                parsed, detected = _parse(
                    reply, window, None if whole else index, self._label
                )
                language = language or detected
                segments.extend(parsed)
        return TranscriptionResult(
            segments=tuple(segments), language=language or options.language
        )

    def _limit(self, spec: OpenAIModelSpec) -> int:
        return self._max_upload_bytes or spec.max_upload_bytes

    def _plan(
        self,
        total_ms: int,
        frame_bytes: int,
        rate: int,
        options: TranscriptionOptions,
        spec: OpenAIModelSpec,
        payload_size: int,
    ) -> list[_Window]:
        """One window if the WAV fits, else overlapping windows owned by midpoint."""
        start = 0
        end = total_ms
        if options.clip is not None:
            start, end = (
                min(options.clip.start_ms, total_ms),
                min(options.clip.end_ms, total_ms),
            )
        if end <= start:
            return []
        if options.clip is None and payload_size <= self._limit(spec):
            return [_Window(0, end, 0, end)]
        usable_ms = (self._limit(spec) - _HEADER_MARGIN_BYTES) // frame_bytes * 1000
        chunk_ms = usable_ms // rate - 2 * self._overlap_ms
        if chunk_ms <= 0:
            raise _fail(f"The {self._label} upload limit is too small for this audio.")
        return [
            _Window(
                start + chunk.process_start_ms,
                start + chunk.process_end_ms,
                start + chunk.owned_start_ms,
                start + chunk.owned_end_ms,
            )
            for chunk in plan_audio_chunks(
                end - start, chunk_duration_ms=chunk_ms, overlap_ms=self._overlap_ms
            )
        ]

    def _post(
        self,
        wav: bytes,
        key: str | None,
        spec: OpenAIModelSpec,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None,
    ) -> bytes:
        fields = [("model", spec.model_id), ("response_format", spec.response_format)]
        if spec.diarized:
            fields.append(("chunking_strategy", "auto"))
        else:
            fields.append(("timestamp_granularities[]", "segment"))
        if options.language is not None:
            fields.append(("language", options.language.split("-")[0].lower()))
        # The diarized model rejects ``prompt``; the others take it as style context.
        if options.prompt and not spec.diarized:
            fields.append(("prompt", options.prompt))
        body, content_type = encode_multipart(
            fields, "file", "audio.wav", "audio/wav", wav
        )
        headers = {"Content-Type": content_type}
        if key is not None:
            headers["Authorization"] = f"Bearer {key}"
        request = HttpRequest(
            self._endpoint,
            headers,
            body,
            self._timeout_s,
            abort=None if cancellation is None else cancellation.is_cancelled,
        )
        for attempt in range(1, self._max_attempts + 1):
            self._check(cancellation)
            retry_after: float | None = None
            try:
                reply = self._transport(request)
            except TransportError as error:
                if error.aborted:
                    raise _cancelled() from None
                # Only timeouts are recoverable; other network errors are not retried.
                if error.oversized:
                    failure = _fail(f"{self._label} returned an oversized response.")
                else:
                    failure = _fail(
                        f"{self._label} did not answer in time."
                        if error.timeout
                        else f"{self._label} could not be reached.",
                        retryable=True,
                    )
                recoverable = error.timeout
            else:
                if reply.status == 200:
                    return reply.body
                failure, recoverable = _http_failure(reply.status, self._label)
                retry_after = _retry_after(reply.headers)
            if not recoverable or attempt == self._max_attempts:
                raise failure
            self._backoff(attempt, retry_after, cancellation)
        raise AssertionError("unreachable")  # pragma: no cover

    def _backoff(
        self,
        attempt: int,
        retry_after: float | None,
        cancellation: TranscriptionCancellationToken | None,
    ) -> None:
        ceiling = min(self._max_delay_s, self._base_delay_s * 2 ** (attempt - 1))
        delay = ceiling / 2 + self._jitter() * ceiling / 2
        if retry_after is not None:
            delay = min(self._max_delay_s, max(delay, retry_after))
        while delay > 0:
            step = min(delay, _SLEEP_SLICE_S)
            self._sleep(step)
            delay -= step
            self._check(cancellation)

    @staticmethod
    def _check(cancellation: TranscriptionCancellationToken | None) -> None:
        if cancellation is not None and cancellation.is_cancelled():
            raise _cancelled()


def _http_failure(status: int, label: str) -> tuple[TranscriptionError, bool]:
    """Map a non-200 status; only 429/5xx are recoverable, never auth/validation."""
    if status in (401, 403):
        return _fail(f"{label} rejected the API key."), False
    if status == 413:
        return _fail(f"The audio exceeds the {label} upload limit."), False
    if status == 429:
        return _fail(f"{label} rate limit reached.", retryable=True), True
    if status >= 500:
        return _fail(f"{label} is temporarily unavailable.", retryable=True), True
    return _fail(f"{label} rejected the request."), False


def _retry_after(headers: Mapping[str, str]) -> float | None:
    for name, value in headers.items():
        if name.lower() == "retry-after":
            try:
                seconds = float(value)
            except ValueError:
                return None
            return seconds if math.isfinite(seconds) and seconds >= 0 else None
    return None


def _slice(source: wave.Wave_read, rate: int, window: _Window) -> bytes:
    first = window.process_start_ms * rate // 1000
    last = min(source.getnframes(), window.process_end_ms * rate // 1000)
    source.setpos(first)
    frames = source.readframes(last - first)
    out = BytesIO()
    with wave.open(out, "wb") as target:
        target.setnchannels(source.getnchannels())
        target.setsampwidth(source.getsampwidth())
        target.setframerate(rate)
        target.writeframes(frames)
    return out.getvalue()


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _parse(
    raw: bytes, window: _Window, chunk_index: int | None, label: str = "OpenAI"
) -> tuple[list[TranscriptionSegment], str | None]:
    """Canonical segments on the global timeline, owned by ``window`` only.

    ``chunk_index`` namespaces diarization labels when the audio was split,
    because ``A`` in one request is not guaranteed to be ``A`` in the next.
    """
    try:
        document = cast(object, json.loads(raw))
    except (UnicodeDecodeError, ValueError):
        raise _fail(f"{label} returned an unreadable response.") from None
    if not isinstance(document, dict):
        raise _fail(f"{label} returned an unexpected response.")
    body = cast(dict[str, object], document)
    items = body.get("segments")
    plain = body.get("text")
    if "segments" not in body and isinstance(plain, str):
        # Plain ``json`` answer of some compatible servers: one segment over the
        # owned span. ponytail: split audio may repeat the overlap's words.
        owned = (window.owned_end_ms - window.owned_start_ms) / 1000
        items = [{"start": 0.0, "end": owned, "text": plain}]
        window = _Window(*([window.owned_start_ms, window.owned_end_ms] * 2))
    if not isinstance(items, list):
        raise _fail(f"{label} returned an unexpected response.")
    found: list[TranscriptionSegment] = []
    shared = (window.process_start_ms, window.process_end_ms) != (
        window.owned_start_ms,
        window.owned_end_ms,
    )
    cursor = window.owned_start_ms
    for item in cast(list[object], items):
        if not isinstance(item, dict):
            continue
        entry = cast(dict[str, object], item)
        start, end, text = (
            _number(entry.get("start")),
            _number(entry.get("end")),
            entry.get("text"),
        )
        if start is None or end is None or not isinstance(text, str):
            raise _fail(f"{label} returned an unexpected response.")
        if not text.strip():
            continue
        start_ms = window.process_start_ms + round(start * 1000)
        end_ms = window.process_start_ms + round(end * 1000)
        middle = (start_ms + end_ms) / 2
        if shared and not window.owned_start_ms <= middle < window.owned_end_ms:
            continue  # midpoint ownership: the neighbouring window keeps it
        start_ms = max(start_ms, cursor, window.owned_start_ms)
        end_ms = min(end_ms, window.owned_end_ms)
        if end_ms <= start_ms:
            continue
        cursor = end_ms
        tag = entry.get("speaker")
        speaker = None if tag is None else str(tag)
        if speaker is not None and chunk_index is not None:
            speaker = f"{chunk_index + 1}:{speaker}"
        found.append(TranscriptionSegment(start_ms, end_ms, text, speaker=speaker))
    return found, _language_code(body.get("language"))


def _language_code(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    name = value.strip().lower()
    if name in _LANGUAGE_CODES:
        return _LANGUAGE_CODES[name]
    return name if _CODE.fullmatch(name) else None


__all__ = ["ENDPOINT", "OpenAITranscriptionProvider"]
