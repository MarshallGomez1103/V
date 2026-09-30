"""OpenAI adapter against a fake transport: nothing here touches the network."""

import json
import re
import threading
import wave
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO

import pytest

from voz.application.ports.transcription import (
    TranscriptionClip,
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
)
from voz.infrastructure.cloud.openai_fake import FakeOpenAITransport
from voz.infrastructure.cloud.openai_limits import (
    LIMITS_DATE,
    LIMITS_SOURCE,
    OPENAI_MODELS,
    PRICE_SOURCE,
    openai_descriptors,
    openai_prices,
)
from voz.infrastructure.cloud.openai_transcription import OpenAITranscriptionProvider
from voz.infrastructure.cloud.openai_transport import (
    HttpRequest,
    HttpResponse,
    TransportError,
    encode_multipart,
    urllib_transport,
)

KEY = "sk-unit-secret-key-42"
WHISPER, DIARIZE = openai_descriptors()


class _Secrets:
    def __init__(self, key: str | None = KEY) -> None:
        self.key = key

    def get(self, provider_id: str) -> str | None:
        return self.key

    def configured(self, provider_id: str) -> bool:
        return self.key is not None

    def set(self, provider_id: str, key: str) -> None:
        raise AssertionError

    def delete(self, provider_id: str) -> None:
        raise AssertionError


class _Cancel:
    def __init__(self, after_sleeps: int | None = None) -> None:
        self.sleeps = 0
        self.after = after_sleeps

    def is_cancelled(self) -> bool:
        return self.after is not None and self.sleeps >= self.after


def _wav(ms: int, *, rate: int = 16_000, ramp: bool = False) -> bytes:
    """Mono PCM16; with ``ramp`` the sample at frame f encodes its millisecond."""
    frames = ms * rate // 1000
    if ramp:
        samples = b"".join(
            ((f * 1000 // rate) % 30_000).to_bytes(2, "little") for f in range(frames)
        )
    else:
        samples = b"\x00\x00" * frames
    out = BytesIO()
    with wave.open(out, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(samples)
    return out.getvalue()


def _provider(
    transport: Callable[[HttpRequest], HttpResponse],
    *,
    secrets: _Secrets | None = None,
    sleeps: list[float] | None = None,
    jitter: float = 1.0,
    max_upload_bytes: int | None = None,
    overlap_ms: int = 2_000,
    max_attempts: int = 4,
    max_delay_s: float = 30.0,
) -> OpenAITranscriptionProvider:
    record = [] if sleeps is None else sleeps
    return OpenAITranscriptionProvider(
        secrets=secrets or _Secrets(),
        transport=transport,
        sleep=record.append,
        jitter=lambda: jitter,
        max_upload_bytes=max_upload_bytes,
        overlap_ms=overlap_ms,
        max_attempts=max_attempts,
        max_delay_s=max_delay_s,
    )


def _options(model: object = WHISPER, **kwargs: object) -> TranscriptionOptions:
    return TranscriptionOptions(model=model, **kwargs)  # type: ignore[arg-type]


def _parts(request: HttpRequest) -> tuple[dict[str, str], bytes]:
    boundary = request.headers["Content-Type"].split("boundary=")[1].encode()
    fields: dict[str, str] = {}
    audio = b""
    for chunk in request.body.split(b"--" + boundary)[1:-1]:
        head, _, content = chunk.partition(b"\r\n\r\n")
        content = content.removesuffix(b"\r\n")
        name = re.search(rb'name="([^"]+)"', head)
        assert name is not None
        if name.group(1) == b"file":
            audio = content
        else:
            fields[name.group(1).decode()] = content.decode()
    return fields, audio


def _close(left: float, right: float) -> bool:
    return abs(left - right) < 1e-9


def _reply(payload: object, status: int = 200) -> HttpResponse:
    return HttpResponse(status, json.dumps(payload).encode())


def test_request_shape_for_whisper_and_canonical_result() -> None:
    fake = FakeOpenAITransport()
    result = _provider(fake).transcribe(
        audio=BytesIO(_wav(1_000)), options=_options(language="es-CO")
    )
    assert fake.calls == 1
    request = fake.requests[0]
    assert request.url == "https://api.openai.com/v1/audio/transcriptions"
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    fields, audio = _parts(request)
    assert fields == {
        "model": "whisper-1",
        "response_format": "verbose_json",
        "timestamp_granularities[]": "segment",
        "language": "es",
    }
    assert audio == _wav(1_000)
    assert [(s.start_ms, s.end_ms, s.text) for s in result.segments] == [
        (0, 100, "hola"),
        (100, 250, " mundo"),
    ]
    assert result.language == "es"
    assert all(s.speaker is None for s in result.segments)


def test_diarized_model_uses_diarized_json_and_keeps_speakers() -> None:
    fake = FakeOpenAITransport()
    result = _provider(fake).transcribe(
        audio=BytesIO(_wav(1_000)), options=_options(DIARIZE)
    )
    fields, _ = _parts(fake.requests[0])
    assert fields["model"] == "gpt-4o-transcribe-diarize"
    assert fields["response_format"] == "diarized_json"
    assert fields["chunking_strategy"] == "auto"
    assert "timestamp_granularities[]" not in fields
    assert [s.speaker for s in result.segments] == ["A", "B"]


def test_request_repr_hides_key_and_audio() -> None:
    fake = FakeOpenAITransport()
    _provider(fake).transcribe(audio=BytesIO(_wav(200)), options=_options())
    assert KEY not in repr(fake.requests[0])
    assert "audio" not in repr(fake.requests[0]).lower().replace("audio/", "")


def _ramp_transport(
    diarized: bool = False, sizes: list[int] | None = None
) -> Callable[[HttpRequest], HttpResponse]:
    """Answer with 400 ms segments every 500 ms whose text is their global start."""

    def transport(request: HttpRequest) -> HttpResponse:
        _, audio = _parts(request)
        if sizes is not None:
            sizes.append(len(request.body))
        with wave.open(BytesIO(audio), "rb") as source:
            base = int.from_bytes(source.readframes(1), "little")
            duration = source.getnframes() * 1000 // source.getframerate()
        segments: list[dict[str, object]] = [
            {"start": k / 2, "end": k / 2 + 0.4, "text": str(base + k * 500)}
            for k in range(duration // 500)
            if k * 500 + 400 <= duration
        ]
        if diarized:
            for segment in segments:
                segment["speaker"] = "A"
        return _reply({"language": "spanish", "segments": segments})

    return transport


def test_large_audio_is_split_with_global_offsets_and_no_overlap() -> None:
    sizes: list[int] = []
    limit = 4 * 32_000 + 1_024  # 4 s of audio per request
    provider = _provider(
        _ramp_transport(sizes=sizes), max_upload_bytes=limit, overlap_ms=1_000
    )
    audio = _wav(10_000, ramp=True)
    assert len(audio) > limit

    result = provider.transcribe(audio=BytesIO(audio), options=_options())

    assert len(sizes) == 5
    assert max(sizes) < limit + 1_000  # multipart framing only
    assert [s.start_ms for s in result.segments] == list(range(0, 10_000, 500))
    assert all(s.text == str(s.start_ms) for s in result.segments)
    assert all(
        a.end_ms <= b.start_ms
        for a, b in zip(result.segments, result.segments[1:], strict=False)
    )
    assert result.language == "es"


def test_split_namespaces_speaker_labels_per_request() -> None:
    provider = _provider(
        _ramp_transport(diarized=True),
        max_upload_bytes=4 * 32_000 + 1_024,
        overlap_ms=1_000,
    )
    result = provider.transcribe(
        audio=BytesIO(_wav(10_000, ramp=True)), options=_options(DIARIZE)
    )
    speakers = {s.speaker for s in result.segments}
    assert speakers == {"1:A", "2:A", "3:A", "4:A", "5:A"}


def test_clip_sends_only_the_window_and_keeps_the_audio_timeline() -> None:
    sizes: list[int] = []
    provider = _provider(_ramp_transport(sizes=sizes))
    result = provider.transcribe(
        audio=BytesIO(_wav(10_000, ramp=True)),
        options=_options(clip=TranscriptionClip(2_000, 4_000)),
    )
    assert len(sizes) == 1
    assert sizes[0] < 2_500 * 32
    assert [s.start_ms for s in result.segments] == [2_000, 2_500, 3_000, 3_500]


def test_empty_audio_returns_empty_result_without_requests() -> None:
    fake = FakeOpenAITransport()
    result = _provider(fake).transcribe(audio=BytesIO(_wav(0)), options=_options())
    assert result.segments == ()
    assert fake.calls == 0


def test_retries_recoverable_failures_with_exponential_backoff() -> None:
    sleeps: list[float] = []
    fake = FakeOpenAITransport(
        [
            HttpResponse(429, b"{}"),
            HttpResponse(503, b"{}"),
            TransportError(timeout=True),
        ]
    )
    result = _provider(fake, sleeps=sleeps, jitter=1.0).transcribe(
        audio=BytesIO(_wav(500)), options=_options()
    )
    assert fake.calls == 4
    assert result.text == "hola mundo"
    assert _close(sum(sleeps), 1.0 + 2.0 + 4.0)


def test_backoff_is_jittered_and_capped() -> None:
    sleeps: list[float] = []
    fake = FakeOpenAITransport([HttpResponse(500, b"")] * 5)
    provider = _provider(
        fake, sleeps=sleeps, jitter=0.0, max_attempts=5, max_delay_s=3.0
    )
    with pytest.raises(TranscriptionError):
        provider.transcribe(audio=BytesIO(_wav(500)), options=_options())
    # Half of the exponential ceiling (1, 2, 3, 3) with zero jitter.
    assert _close(sum(sleeps), 0.5 + 1.0 + 1.5 + 1.5)


def test_retry_after_is_honored_up_to_the_cap() -> None:
    sleeps: list[float] = []
    fake = FakeOpenAITransport([HttpResponse(429, b"{}", {"Retry-After": "7"})])
    _provider(fake, sleeps=sleeps, jitter=0.0).transcribe(
        audio=BytesIO(_wav(500)), options=_options()
    )
    assert _close(sum(sleeps), 7.0)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 422])
def test_client_errors_are_never_retried(status: int) -> None:
    sleeps: list[float] = []
    fake = FakeOpenAITransport([HttpResponse(status, b'{"error": "secret body"}')])
    with pytest.raises(TranscriptionError) as raised:
        _provider(fake, sleeps=sleeps).transcribe(
            audio=BytesIO(_wav(500)), options=_options()
        )
    assert fake.calls == 1
    assert sleeps == []
    assert raised.value.code is TranscriptionFailureCode.PROVIDER_FAILED
    assert raised.value.retryable is False
    assert "secret body" not in raised.value.user_message
    assert KEY not in raised.value.user_message


def test_exhausted_retries_raise_a_retryable_typed_error() -> None:
    fake = FakeOpenAITransport([HttpResponse(429, b"{}")] * 4)
    with pytest.raises(TranscriptionError) as raised:
        _provider(fake).transcribe(audio=BytesIO(_wav(500)), options=_options())
    assert fake.calls == 4
    assert raised.value.retryable is True
    assert raised.value.code is TranscriptionFailureCode.PROVIDER_FAILED


def test_network_errors_other_than_timeouts_are_not_retried() -> None:
    fake = FakeOpenAITransport([TransportError()])
    with pytest.raises(TranscriptionError) as raised:
        _provider(fake).transcribe(audio=BytesIO(_wav(500)), options=_options())
    assert fake.calls == 1
    assert raised.value.retryable is True


def test_cancellation_during_backoff_stops_before_another_request() -> None:
    cancel = _Cancel(after_sleeps=1)
    fake = FakeOpenAITransport([HttpResponse(500, b"")] * 3)
    provider = OpenAITranscriptionProvider(
        secrets=_Secrets(),
        transport=fake,
        sleep=lambda _: setattr(cancel, "sleeps", cancel.sleeps + 1),
        jitter=lambda: 1.0,
    )
    with pytest.raises(TranscriptionError) as raised:
        provider.transcribe(
            audio=BytesIO(_wav(500)), options=_options(), cancellation=cancel
        )
    assert raised.value.code is TranscriptionFailureCode.CANCELLED
    assert fake.calls == 1


def test_cancellation_between_split_requests() -> None:
    cancel = _Cancel()
    calls: list[int] = []

    def transport(request: HttpRequest) -> HttpResponse:
        calls.append(1)
        cancel.after = 0  # cancelled right after the first upload
        return _ramp_transport()(request)

    provider = _provider(
        transport, max_upload_bytes=4 * 32_000 + 1_024, overlap_ms=1_000
    )
    with pytest.raises(TranscriptionError) as raised:
        provider.transcribe(
            audio=BytesIO(_wav(10_000, ramp=True)),
            options=_options(),
            cancellation=cancel,
        )
    assert raised.value.code is TranscriptionFailureCode.CANCELLED
    assert len(calls) == 1


def test_missing_key_fails_without_any_request() -> None:
    fake = FakeOpenAITransport()
    with pytest.raises(TranscriptionError) as raised:
        _provider(fake, secrets=_Secrets(None)).transcribe(
            audio=BytesIO(_wav(500)), options=_options()
        )
    assert raised.value.code is TranscriptionFailureCode.PROVIDER_FAILED
    assert fake.calls == 0


def test_foreign_or_unknown_model_is_rejected_without_requests() -> None:
    fake = FakeOpenAITransport()
    foreign = openai_descriptors()[0].__class__(
        provider_id="faster-whisper",
        model_id="whisper-1",
        display_name="Local",
        capabilities=WHISPER.capabilities,
    )
    unknown = openai_descriptors()[0].__class__(
        provider_id="openai",
        model_id="gpt-unknown",
        display_name="Unknown",
        capabilities=WHISPER.capabilities,
    )
    for model in (foreign, unknown):
        with pytest.raises(TranscriptionError) as raised:
            _provider(fake).transcribe(
                audio=BytesIO(_wav(500)), options=_options(model)
            )
        assert raised.value.code is TranscriptionFailureCode.MODEL_NOT_INSTALLED
    assert fake.calls == 0


@pytest.mark.parametrize(
    "raw",
    [b"not json", b"[]", b'{"segments": "x"}', b'{"segments": [{"start": 0}]}'],
)
def test_malformed_responses_are_typed_failures(raw: bytes) -> None:
    fake = FakeOpenAITransport([HttpResponse(200, raw)])
    with pytest.raises(TranscriptionError) as raised:
        _provider(fake).transcribe(audio=BytesIO(_wav(500)), options=_options())
    assert raised.value.code is TranscriptionFailureCode.PROVIDER_FAILED
    assert raised.value.retryable is False


def test_response_quirks_are_normalized_without_altering_text() -> None:
    fake = FakeOpenAITransport(
        [
            _reply(
                {
                    "language": "klingon",
                    "segments": [
                        {"start": 0.0, "end": 1.0, "text": " uno"},
                        {"start": 0.5, "end": 2.0, "text": " dos"},
                        {"start": 2.0, "end": 2.0, "text": " cero"},
                        {"start": 2.0, "end": 3.0, "text": "   "},
                    ],
                }
            )
        ]
    )
    result = _provider(fake).transcribe(
        audio=BytesIO(_wav(3_000)), options=_options(language="es")
    )
    assert [(s.start_ms, s.end_ms, s.text) for s in result.segments] == [
        (0, 1_000, " uno"),
        (1_000, 2_000, " dos"),
    ]
    assert result.language == "es"  # unknown name falls back to the requested tag


@pytest.mark.parametrize("payload", [b"not-a-wave", b""])
def test_invalid_audio_is_typed_and_sends_nothing(payload: bytes) -> None:
    fake = FakeOpenAITransport()
    with pytest.raises(TranscriptionError) as raised:
        _provider(fake).transcribe(audio=BytesIO(payload), options=_options())
    assert raised.value.code is TranscriptionFailureCode.INVALID_AUDIO
    assert fake.calls == 0


def test_dated_limits_and_prices_are_documented_as_unverified() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", LIMITS_DATE)
    assert "no verificado en vivo" in LIMITS_SOURCE
    assert "no verificado en vivo" in PRICE_SOURCE
    assert all(spec.max_upload_bytes == 25_000_000 for spec in OPENAI_MODELS)
    assert set(openai_prices()) == {("openai", s.model_id) for s in OPENAI_MODELS}


def test_default_limit_is_overridable() -> None:
    fake = FakeOpenAITransport()
    _provider(fake, max_upload_bytes=10 * 1024 * 1024).transcribe(
        audio=BytesIO(_wav(500)), options=_options()
    )
    assert fake.calls == 1


def test_multipart_encoding_round_trips() -> None:
    body, content_type = encode_multipart(
        [("model", "whisper-1"), ("language", "es")],
        "file",
        "audio.wav",
        "audio/wav",
        b"RIFF\r\n--not-a-boundary\x00\xff",
    )
    request = HttpRequest("https://x.invalid", {"Content-Type": content_type}, body)
    fields, audio = _parts(request)
    assert fields == {"model": "whisper-1", "language": "es"}
    assert audio == b"RIFF\r\n--not-a-boundary\x00\xff"


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        self.rfile.read(length)
        if self.path == "/slow":
            threading.Event().wait(0.5)
        status = 429 if self.path == "/limited" else 200
        self.send_response(status)
        self.send_header("Retry-After", "2")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def local_server() -> object:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def test_urllib_transport_against_a_loopback_server(local_server: str) -> None:
    ok = urllib_transport(HttpRequest(f"{local_server}/ok", {"X": "1"}, b"data", 5))
    limited = urllib_transport(HttpRequest(f"{local_server}/limited", {}, b"x", 5))
    assert (ok.status, ok.body) == (200, b'{"ok": true}')
    assert limited.status == 429
    assert limited.headers["Retry-After"] == "2"
    with pytest.raises(TransportError) as slow:
        urllib_transport(HttpRequest(f"{local_server}/slow", {}, b"x", 0.1))
    assert slow.value.timeout is True


def test_urllib_transport_maps_connection_refused() -> None:
    with pytest.raises(TransportError) as raised:
        urllib_transport(HttpRequest("http://127.0.0.1:9/x", {}, b"x", 2))
    assert raised.value.timeout is False
