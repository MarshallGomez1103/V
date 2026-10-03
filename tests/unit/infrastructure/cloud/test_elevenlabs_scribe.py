"""ElevenLabs Scribe adapter behind a fake transport: no network, no billing."""

from __future__ import annotations

import http.server
import json
import logging
import sys
import threading
import wave
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

from voz.application.ports.provider_secrets import (
    ProviderSecretsPort,
    SecretsError,
    SecretsFailureCode,
)
from voz.application.ports.transcription import (
    TranscriptionClip,
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
    TranscriptionProvider,
    TranscriptionResult,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.infrastructure.cloud.elevenlabs_scribe import (
    SCRIBE_URL,
    ElevenLabsScribeProvider,
    elevenlabs_scribe_descriptor,
    normalize_keyterms,
)
from voz.infrastructure.cloud.elevenlabs_transport import (
    HttpRequest,
    HttpResponse,
    TransportError,
    http_transport,
)
from voz.infrastructure.secrets import ProviderSecrets

KEY = "xi-secret-key-123"
VALID_AUDIO = Path(__file__).parents[3] / "fixtures/media/synthetic-tone.wav"


def _word(
    text: str, start: float, end: float, speaker: str = "speaker_0"
) -> dict[str, Any]:
    return {
        "text": text,
        "start": start,
        "end": end,
        "type": "word",
        "speaker_id": speaker,
    }


def _space(start: float, end: float) -> dict[str, Any]:
    return {"text": " ", "start": start, "end": end, "type": "spacing"}


class _Secrets:
    def __init__(self, key: str | None = KEY, error: SecretsError | None = None):
        self.key = key
        self.error = error

    def get(self, provider_id: str) -> str | None:
        assert provider_id == "elevenlabs"
        if self.error is not None:
            raise self.error
        return self.key

    def configured(self, provider_id: str) -> bool:
        return self.key is not None

    def set(self, provider_id: str, key: str) -> None:
        raise AssertionError

    def delete(self, provider_id: str) -> None:
        raise AssertionError


class _FakeTransport:
    """Records each request (with its drained body); answers a canned response."""

    def __init__(
        self,
        payload: object | None = None,
        *,
        status: int = 200,
        raw: bytes | None = None,
        error: TransportError | None = None,
    ) -> None:
        self.payload: object = payload if payload is not None else {"words": []}
        self.status = status
        self.raw = raw
        self.error = error
        self.requests: list[HttpRequest] = []
        self.bodies: list[bytes] = []

    def __call__(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        chunks: list[bytes] = []
        while chunk := request.body.read(4096):
            chunks.append(chunk)
        body = b"".join(chunks)
        assert len(body) == request.content_length
        self.bodies.append(body)
        if self.error is not None:
            raise self.error
        raw = self.raw if self.raw is not None else json.dumps(self.payload).encode()
        return HttpResponse(self.status, raw)


class _Cancelled:
    def __init__(self, requested: bool = True) -> None:
        self.requested = requested

    def is_cancelled(self) -> bool:
        return self.requested


def _options(**kwargs: object) -> TranscriptionOptions:
    return TranscriptionOptions(model=elevenlabs_scribe_descriptor(), **kwargs)  # type: ignore[arg-type]


def _provider(
    transport: _FakeTransport,
    secrets: ProviderSecretsPort | None = None,
    **kwargs: object,
) -> ElevenLabsScribeProvider:
    return ElevenLabsScribeProvider(
        secrets=_Secrets() if secrets is None else secrets,
        transport=transport,
        **kwargs,  # type: ignore[arg-type]
    )


def _run(
    provider: ElevenLabsScribeProvider, options: TranscriptionOptions | None = None
) -> TranscriptionResult:
    with VALID_AUDIO.open("rb") as audio:
        return provider.transcribe(
            audio=audio, options=_options() if options is None else options
        )


def _wav(seconds: float, rate: int = 16_000) -> bytes:
    out = BytesIO()
    with wave.open(out, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(b"\x00\x00" * int(seconds * rate))
    return out.getvalue()


def _fields(body: bytes) -> list[tuple[str, str]]:
    """Text fields of the multipart body (the file part is skipped)."""
    fields: list[tuple[str, str]] = []
    for part in body.split(b"--voz-")[1:-1]:
        head, _, rest = part.partition(b"\r\n\r\n")
        if b"filename=" in head:
            continue
        name = head.split(b'name="')[1].split(b'"')[0].decode()
        fields.append((name, rest.rsplit(b"\r\n", 1)[0].decode()))
    return fields


# --- S12.01: key via ProviderSecrets (provider_id "elevenlabs") --------------


def test_provider_reads_the_key_from_the_environment(tmp_path: Path) -> None:
    secrets = ProviderSecrets(tmp_path, environ={"ELEVENLABS_API_KEY": KEY})
    transport = _FakeTransport()

    _run(_provider(transport, secrets))

    assert transport.requests[0].headers["xi-api-key"] == KEY


def test_provider_reads_the_key_from_the_secrets_file(tmp_path: Path) -> None:
    secrets = ProviderSecrets(tmp_path / "cfg", environ={})
    secrets.set("elevenlabs", KEY)
    transport = _FakeTransport()

    _run(_provider(transport, secrets))

    assert transport.requests[0].headers["xi-api-key"] == KEY


def test_without_a_key_the_provider_is_unavailable_and_sends_nothing(
    tmp_path: Path,
) -> None:
    transport = _FakeTransport()
    provider = _provider(transport, ProviderSecrets(tmp_path, environ={}))

    with pytest.raises(TranscriptionError) as raised:
        _run(provider)

    assert raised.value.code is TranscriptionFailureCode.PROVIDER_FAILED
    assert raised.value.user_message == "The ElevenLabs API key is not configured."
    assert transport.requests == []


def test_unreadable_secrets_file_is_a_safe_failure() -> None:
    transport = _FakeTransport()
    secrets = _Secrets(
        error=SecretsError(SecretsFailureCode.FILE_INSECURE, "/home/u/secrets.toml")
    )

    with pytest.raises(TranscriptionError) as raised:
        _run(_provider(transport, secrets))

    assert raised.value.user_message == "The ElevenLabs API key could not be read."
    assert "/home" not in str(raised.value)
    assert transport.requests == []


def test_key_present_does_not_activate_anything_by_itself() -> None:
    transport = _FakeTransport()

    provider = _provider(transport)

    assert isinstance(provider, TranscriptionProvider)
    assert transport.requests == []
    assert KEY not in repr(provider) + str(provider)


def test_another_providers_model_is_rejected_before_any_request() -> None:
    transport = _FakeTransport()
    other = ModelDescriptor(
        provider_id="openai",
        model_id="whisper-1",
        display_name="Other",
        capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    )

    with pytest.raises(TranscriptionError) as raised:
        _run(_provider(transport), TranscriptionOptions(model=other))

    assert raised.value.code is TranscriptionFailureCode.MODEL_NOT_INSTALLED
    assert transport.requests == []


# --- S12.02: request shape ---------------------------------------------------


def test_request_is_a_multipart_post_to_scribe_with_the_key_header() -> None:
    transport = _FakeTransport()

    _run(_provider(transport), _options(language="es-CO"))

    request = transport.requests[0]
    assert request.url == SCRIBE_URL == "https://api.elevenlabs.io/v1/speech-to-text"
    assert request.headers["xi-api-key"] == KEY
    assert request.headers["Content-Type"].startswith("multipart/form-data; boundary=")
    fields = dict(_fields(transport.bodies[0]))
    assert fields == {
        "model_id": "scribe_v1",
        "diarize": "true",
        "timestamps_granularity": "word",
        "tag_audio_events": "false",
        "language_code": "es",
    }
    assert b'name="file"; filename="audio.wav"' in transport.bodies[0]
    assert VALID_AUDIO.read_bytes() in transport.bodies[0]
    assert KEY not in repr(request)


def test_language_is_omitted_when_not_requested_and_diarize_is_configurable() -> None:
    transport = _FakeTransport()

    _run(_provider(transport, diarize=False))

    fields = dict(_fields(transport.bodies[0]))
    assert "language_code" not in fields
    assert fields["diarize"] == "false"


# --- S12.03 / S12.04: diarization and words ----------------------------------


PAYLOAD = {
    "language_code": "spa",
    "words": [
        _word("Hola", 0.0, 0.4),
        _space(0.4, 0.5),
        _word("mundo.", 0.5, 0.9),
        _space(0.9, 1.0),
        _word("Bien", 1.0, 1.3),  # after final punctuation: new segment
        _space(1.3, 1.4),
        _word("gracias", 1.4, 1.8),
        _word("y", 3.0, 3.1),  # pause > 0.8 s: new segment
        {"text": "(risas)", "start": 3.1, "end": 3.2, "type": "audio_event"},
        _space(3.1, 3.2),
        _word("tú", 3.2, 3.5, "speaker_1"),  # speaker change: new segment
    ],
}


def test_words_are_grouped_by_punctuation_pauses_and_speaker() -> None:
    result = _run(_provider(_FakeTransport(PAYLOAD)))

    assert [(s.speaker, s.text) for s in result.segments] == [
        ("speaker_0", "Hola mundo."),
        ("speaker_0", " Bien gracias"),
        ("speaker_0", "y"),
        ("speaker_1", " tú"),
    ]
    assert result.language == "es"
    assert result.text == "Hola mundo. Bien gracias" + "y" + " tú"


def test_words_are_canonical_monotonic_milliseconds_inside_their_segment() -> None:
    result = _run(_provider(_FakeTransport(PAYLOAD)))

    first = result.segments[0]
    assert (first.start_ms, first.end_ms) == (0, 900)
    assert [(w.start_ms, w.end_ms, w.text) for w in first.words] == [
        (0, 400, "Hola"),
        (500, 900, " mundo."),
    ]
    assert "".join(w.text for s in result.segments for w in s.words) == result.text
    starts = [w.start_ms for s in result.segments for w in s.words]
    assert starts == sorted(starts)


def test_overlapping_speakers_and_zero_length_words_are_made_monotonic() -> None:
    payload = {
        "words": [
            _word("uno", 0.0, 1.0, "a"),
            _word("dos", 0.5, 0.5, "b"),  # overlaps and has no duration
            _word("tres", 0.6, 0.9, "a"),
        ]
    }

    result = _run(_provider(_FakeTransport(payload)))

    spans = [(s.start_ms, s.end_ms) for s in result.segments]
    assert spans == [(0, 1000), (1000, 1001), (1001, 1002)]


def test_word_timestamps_can_be_switched_off() -> None:
    result = _run(_provider(_FakeTransport(PAYLOAD)), _options(word_timestamps=False))

    assert all(segment.words == () for segment in result.segments)


def test_requested_language_wins_over_the_detected_one() -> None:
    result = _run(_provider(_FakeTransport(PAYLOAD)), _options(language="gl"))

    assert result.language == "gl"


def test_clip_sends_only_the_clip_and_restores_the_global_timeline() -> None:
    transport = _FakeTransport({"words": [_word("hola", 0.0, 0.5)]})
    provider = _provider(transport)

    result = provider.transcribe(
        audio=BytesIO(_wav(3)),
        options=_options(clip=TranscriptionClip(start_ms=1000, end_ms=2000)),
    )

    assert (result.segments[0].start_ms, result.segments[0].end_ms) == (1000, 1500)
    assert transport.requests[0].content_length < len(_wav(3))


def test_silent_audio_with_no_words_gives_an_empty_result() -> None:
    result = _run(_provider(_FakeTransport({"text": "", "words": []})))

    assert result.segments == ()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"text": "hola"},
        {"words": "x"},
        {"words": [{"type": "word", "text": "a", "start": "0", "end": 1}]},
        {"words": [{"type": "word", "text": "a", "start": -1, "end": 1}]},
    ],
)
def test_malformed_payload_is_a_typed_failure(payload: object) -> None:
    with pytest.raises(TranscriptionError) as raised:
        _run(_provider(_FakeTransport(payload)))

    assert raised.value.code is TranscriptionFailureCode.PROVIDER_FAILED
    assert raised.value.user_message == "ElevenLabs returned an unexpected response."


def test_non_json_body_is_a_typed_failure() -> None:
    with pytest.raises(TranscriptionError) as raised:
        _run(_provider(_FakeTransport(raw=b"<html>secret transcript</html>")))

    assert raised.value.code is TranscriptionFailureCode.PROVIDER_FAILED
    assert "secret" not in str(raised.value)


# --- S12.05: keyterms ---------------------------------------------------------


def test_keyterms_become_repeated_request_fields() -> None:
    transport = _FakeTransport()

    _run(_provider(transport, keyterms=[" Mitocondria ", "", "VOZ", "VOZ"]))

    terms = [v for k, v in _fields(transport.bodies[0]) if k == "keyterms"]
    assert terms == ["Mitocondria", "VOZ"]


def test_no_keyterms_no_field() -> None:
    transport = _FakeTransport()

    _run(_provider(transport))

    assert all(name != "keyterms" for name, _ in _fields(transport.bodies[0]))


def test_keyterm_limits_are_enforced_at_construction() -> None:
    with pytest.raises(ValueError, match="keyterms"):
        normalize_keyterms(["x" * 51])
    with pytest.raises(ValueError, match="keyterms"):
        normalize_keyterms(["bad\nterm"])
    with pytest.raises(ValueError, match="at most"):
        normalize_keyterms([f"t{i}" for i in range(101)])


# --- S12.06: long files, progress, timeout, limits ---------------------------


def test_upload_progress_reports_bytes_sent_up_to_the_total() -> None:
    seen: list[tuple[int, int]] = []
    transport = _FakeTransport()

    def record(sent: int, total: int) -> None:
        seen.append((sent, total))

    _run(_provider(transport, on_upload_progress=record))

    total = transport.requests[0].content_length
    assert seen[-1] == (total, total)
    assert [sent for sent, _ in seen] == sorted(sent for sent, _ in seen)
    assert len(seen) > 1


def test_timeout_is_generous_and_scales_with_the_duration() -> None:
    short, long_ = _FakeTransport(), _FakeTransport()

    _provider(short).transcribe(audio=BytesIO(_wav(1)), options=_options())
    _provider(long_).transcribe(audio=BytesIO(_wav(120)), options=_options())

    assert short.requests[0].timeout_s >= 300
    assert abs(long_.requests[0].timeout_s - short.requests[0].timeout_s - 119) < 0.01
    override = _FakeTransport()
    _provider(override, timeout_s=7).transcribe(
        audio=BytesIO(_wav(1)), options=_options()
    )
    assert override.requests[0].timeout_s == 7


def test_audio_over_the_configured_limit_is_rejected_before_sending() -> None:
    transport = _FakeTransport()

    with pytest.raises(TranscriptionError) as raised:
        _run(_provider(transport, max_upload_bytes=100))

    assert raised.value.code is TranscriptionFailureCode.INVALID_AUDIO
    assert transport.requests == []


def test_cancellation_during_upload_aborts_with_the_cancelled_code() -> None:
    state = _Cancelled(False)

    def transport(request: HttpRequest) -> HttpResponse:
        request.body.read(10)
        state.requested = True
        request.body.read(10)
        raise AssertionError("upload must stop")

    provider = ElevenLabsScribeProvider(secrets=_Secrets(), transport=transport)

    with pytest.raises(TranscriptionError) as raised:
        provider.transcribe(
            audio=BytesIO(_wav(1)), options=_options(), cancellation=state
        )

    assert raised.value.code is TranscriptionFailureCode.CANCELLED


def test_non_seekable_audio_is_buffered() -> None:
    class _Pipe(BytesIO):
        def seekable(self) -> bool:
            return False

    transport = _FakeTransport()

    _provider(transport).transcribe(audio=_Pipe(_wav(1)), options=_options())

    assert len(transport.requests) == 1


# --- failures, privacy ---------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (401, TranscriptionFailureCode.PROVIDER_FAILED, False),
        (403, TranscriptionFailureCode.PROVIDER_FAILED, False),
        (422, TranscriptionFailureCode.PROVIDER_FAILED, False),
        (413, TranscriptionFailureCode.INVALID_AUDIO, False),
        (415, TranscriptionFailureCode.INVALID_AUDIO, False),
        (429, TranscriptionFailureCode.PROVIDER_FAILED, True),
        (503, TranscriptionFailureCode.PROVIDER_FAILED, True),
    ],
)
def test_http_statuses_map_to_stable_codes_without_leaking_the_body(
    status: int, code: TranscriptionFailureCode, retryable: bool
) -> None:
    transport = _FakeTransport(
        raw=b'{"detail": "secret transcript text"}', status=status
    )

    with pytest.raises(TranscriptionError) as raised:
        _run(_provider(transport))

    assert raised.value.code is code
    assert raised.value.retryable is retryable
    assert "secret" not in str(raised.value)
    assert len(transport.requests) == 1  # a billable POST is never auto-retried


@pytest.mark.parametrize("timeout", [True, False])
def test_network_failures_are_retryable_provider_failures(timeout: bool) -> None:
    transport = _FakeTransport(error=TransportError(timeout=timeout))

    with pytest.raises(TranscriptionError) as raised:
        _run(_provider(transport))

    assert raised.value.code is TranscriptionFailureCode.PROVIDER_FAILED
    assert raised.value.retryable is True


def test_the_key_never_reaches_logs_errors_or_results(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    failing = _FakeTransport(status=401, raw=KEY.encode())
    with pytest.raises(TranscriptionError) as raised:
        _run(_provider(failing))
    ok = _run(_provider(_FakeTransport(PAYLOAD)))

    assert KEY not in caplog.text
    assert KEY not in str(raised.value) + repr(raised.value)
    assert KEY not in repr(ok)


def test_cancelled_before_start_sends_nothing_and_reads_nothing() -> None:
    transport = _FakeTransport()
    audio = BytesIO(b"x")

    with pytest.raises(TranscriptionError) as raised:
        _provider(transport).transcribe(
            audio=audio, options=_options(), cancellation=_Cancelled()
        )

    assert raised.value.code is TranscriptionFailureCode.CANCELLED
    assert audio.tell() == 0
    assert transport.requests == []


# --- default transport, against a loopback server (never ElevenLabs) ----------


def test_default_transport_streams_the_body_to_a_local_server() -> None:
    received: dict[str, object] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers["Content-Length"])
            received["body"] = self.rfile.read(length)
            received["key"] = self.headers["xi-api-key"]
            payload = b'{"words": []}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = BytesIO(b"hello")
        response = http_transport(
            HttpRequest(
                url=f"http://127.0.0.1:{server.server_port}/v1/speech-to-text?x=1",
                headers={"xi-api-key": "k"},
                body=body,
                content_length=5,
                timeout_s=5,
            )
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

    assert response == HttpResponse(200, b'{"words": []}')
    assert received == {"body": b"hello", "key": "k"}


def test_default_transport_maps_connection_errors() -> None:
    server = http.server.HTTPServer(
        ("127.0.0.1", 0), http.server.BaseHTTPRequestHandler
    )
    port = server.server_port
    server.server_close()  # nothing listens here any more

    with pytest.raises(TransportError) as raised:
        http_transport(
            HttpRequest(
                url=f"http://127.0.0.1:{port}/",
                headers={},
                body=BytesIO(b""),
                content_length=0,
                timeout_s=2,
            )
        )

    if sys.platform != "win32":
        # Windows retries a refused connection until the timeout expires, so the
        # same failure surfaces there as a timeout; both are transport errors.
        assert raised.value.timeout is False


def test_default_transport_rejects_non_http_urls() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        http_transport(
            HttpRequest(
                url="file:///etc/passwd",
                headers={},
                body=BytesIO(b""),
                content_length=0,
                timeout_s=1,
            )
        )


# --- S13.01: project glossary -------------------------------------------------


def test_glossary_is_sent_as_keyterms_after_the_constructor_ones() -> None:
    transport = _FakeTransport()

    _run(
        _provider(transport, keyterms=["VOZ"]),
        _options(glossary=("Mitocondria", "VOZ")),
    )

    terms = [v for k, v in _fields(transport.bodies[0]) if k == "keyterms"]
    assert terms == ["VOZ", "Mitocondria"]


def test_glossary_over_the_provider_limit_fails_typed() -> None:
    transport = _FakeTransport()
    glossary = tuple(f"t{i}" for i in range(101))

    with pytest.raises(TranscriptionError, match="glossary"):
        _run(_provider(transport), _options(glossary=glossary))
    assert not transport.bodies
