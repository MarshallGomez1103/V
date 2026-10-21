"""OpenAI-compatible engine (V4-04) against the loopback fake server.

The shared STT/TTS contracts run it too; this module covers what is specific:
loopback vs cloud, recorded consent, the key never leaving the header, the
0600 endpoints file, cancellation cutting the request, live edits, WAV
decoding and the default wiring through ``create_app``.
"""

from __future__ import annotations

import json
import logging
import socket
import stat
import struct
import threading
import time
from collections.abc import Generator
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi.testclient import TestClient
from openai_compatible_fake import (
    SAMPLE_RATE,
    TTS_MODEL,
    VOICES,
    FakeServer,
    endpoint_for,
    fake_server,
    setup,
    wav_bytes,
)

from voz.application.ports.compatible_endpoints import (
    CompatibleEndpoint,
    EndpointError,
    EndpointFailureCode,
    is_loopback_url,
)
from voz.application.ports.speech_synthesis import (
    PcmSampleFormat,
    SynthesisError,
    SynthesisFailureCode,
)
from voz.application.ports.transcription import (
    TranscriptionError,
    TranscriptionFailureCode,
)
from voz.bootstrap import create_app
from voz.domain.entities.model_descriptor import ModelCapability
from voz.infrastructure.cloud.compatible_store import (
    ENDPOINTS_FILENAME,
    FileCompatibleEndpointStore,
)
from voz.infrastructure.cloud.openai_compatible import (
    CLOUD_PROVIDER_ID,
    LOCAL_PROVIDER_ID,
    CompatibleModels,
    HttpConnectionTester,
    decode_speech,
)
from voz.infrastructure.cloud.openai_transport import (
    HttpRequest,
    TransportError,
    urllib_transport,
)
from voz.infrastructure.paths import VozPaths

KEY = "sk-compatible-secret-4242"
FIXTURE_WAV = Path(__file__).parents[1] / "fixtures/media/synthetic-tone.wav"


@pytest.fixture
def server() -> Generator[FakeServer]:
    with fake_server(key=KEY) as running:
        yield running


class _CancelLater:
    def __init__(self, after_s: float) -> None:
        self.deadline = time.monotonic() + after_s

    def is_cancelled(self) -> bool:
        return time.monotonic() >= self.deadline


# --- classification and validation -------------------------------------------


@pytest.mark.parametrize(
    ("url", "loopback"),
    [
        ("http://localhost:8880/v1", True),
        ("http://127.0.0.1:8000/v1", True),
        ("http://127.9.8.7/v1", True),
        ("http://[::1]:9000/v1", True),
        ("http://0.0.0.0:8000/v1", False),
        ("http://192.168.1.20:8000/v1", False),
        ("https://api.example.com/v1", False),
        ("http://localhost.example.com/v1", False),
        ("http://127.0.0.1.nip.io/v1", False),
        ("http://[::ffff:127.0.0.1]/v1", True),  # IPv4-mapped loopback
    ],
)
def test_only_loopback_hosts_are_local(url: str, loopback: bool) -> None:
    assert is_loopback_url(url) is loopback


def test_a_non_loopback_endpoint_requires_recorded_consent() -> None:
    values = {"id": "0123456789ab", "name": "Remote", "stt_models": ("m",)}
    with pytest.raises(EndpointError) as raised:
        CompatibleEndpoint(base_url="https://api.example.com/v1", **values)  # type: ignore[arg-type]
    assert raised.value.code is EndpointFailureCode.CONSENT_REQUIRED

    remote = CompatibleEndpoint(
        base_url="https://api.example.com/v1/",
        cloud_consent=True,
        **values,  # type: ignore[arg-type]
    )
    assert remote.cloud and remote.base_url == "https://api.example.com/v1"
    local = CompatibleEndpoint(base_url="http://localhost:1/v1", **values)  # type: ignore[arg-type]
    assert not local.cloud


@pytest.mark.parametrize(
    "changes",
    [
        {"base_url": "ftp://localhost/v1"},
        {"base_url": "http://user:pw@localhost/v1"},
        {"base_url": "http://localhost/v1?x=1"},
        {"base_url": "http:///v1"},
        {"base_url": "http://local host/v1"},
        {"stt_models": (), "tts_models": ()},
        {"tts_voices": ()},
        {"stt_models": ("a", "a")},
        {"name": " padded "},
        {"id": "../etc"},
    ],
)
def test_invalid_endpoints_are_rejected(changes: dict[str, object]) -> None:
    values: dict[str, object] = {
        "id": "0123456789ab",
        "name": "Server",
        "base_url": "http://localhost:8000/v1",
        "stt_models": ("whisper",),
        "tts_models": ("kokoro",),
        "tts_voices": ("af",),
        **changes,
    }
    with pytest.raises(EndpointError) as raised:
        CompatibleEndpoint(**values)  # type: ignore[arg-type]
    assert raised.value.code is EndpointFailureCode.INVALID


@pytest.mark.parametrize(
    ("field", "capability"),
    [
        ("stt_models", ModelCapability.TRANSCRIPTION),
        ("tts_models", ModelCapability.SYNTHESIS),
    ],
)
@pytest.mark.parametrize("length", [242, 243])
def test_model_names_fit_namespaced_descriptor_limit(
    tmp_path: Path, field: str, capability: ModelCapability, length: int
) -> None:
    server = FakeServer("http://127.0.0.1:8000")
    changes = {field: ("m" * length,)}
    if length == 243:
        with pytest.raises(EndpointError) as raised:
            endpoint_for(server, **changes)
        assert raised.value.code is EndpointFailureCode.INVALID
        return

    endpoint = endpoint_for(server, **changes)
    store = FileCompatibleEndpointStore(tmp_path)
    store.save(endpoint)
    models = CompatibleModels(store, capability).list_models()
    assert len(models) == 1
    assert models[0].descriptor.model_id == endpoint.id + "/" + "m" * length
    assert len(models[0].descriptor.model_id) == 255


def test_voice_names_keep_the_255_character_limit() -> None:
    endpoint = endpoint_for(
        FakeServer("http://127.0.0.1:8000"), tts_voices=("v" * 255,)
    )
    assert endpoint.tts_voices == ("v" * 255,)


# --- the 0600 endpoints file ---------------------------------------------------


def test_store_writes_a_private_file_without_keys(
    tmp_path: Path, server: FakeServer
) -> None:
    configured = setup(tmp_path, server, key=KEY)
    file = tmp_path / ENDPOINTS_FILENAME

    assert stat.S_IMODE(file.stat().st_mode) == 0o600
    assert KEY not in file.read_text(encoding="utf-8")
    assert configured.store.get(configured.endpoint.id) == configured.endpoint
    assert str(tmp_path) not in repr(configured.store)
    assert configured.store.delete(configured.endpoint.id) is True
    assert configured.store.delete(configured.endpoint.id) is False
    assert configured.store.list() == ()


def test_store_rejects_an_insecure_or_corrupt_file(tmp_path: Path) -> None:
    store = FileCompatibleEndpointStore(tmp_path)
    file = tmp_path / ENDPOINTS_FILENAME
    file.write_text('{"endpoints": []}', encoding="utf-8")
    file.chmod(0o644)
    with pytest.raises(EndpointError) as raised:
        store.list()
    assert raised.value.code is EndpointFailureCode.FILE_INSECURE

    file.chmod(0o600)
    file.write_text("not json", encoding="utf-8")
    with pytest.raises(EndpointError) as raised:
        store.list()
    assert raised.value.code is EndpointFailureCode.FILE_INVALID
    # The catalogs list nothing instead of failing the options query.
    assert CompatibleModels(store, ModelCapability.SYNTHESIS).list_models() == ()


def test_store_rejects_symlinks_without_changing_the_target(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    original = '{"endpoints": []}'
    target.write_text(original, encoding="utf-8")
    target.chmod(0o600)
    (tmp_path / ENDPOINTS_FILENAME).symlink_to(target)
    store = FileCompatibleEndpointStore(tmp_path)
    endpoint = endpoint_for(FakeServer("http://127.0.0.1:8000"))

    with pytest.raises(EndpointError) as read:
        store.list()
    with pytest.raises(EndpointError) as write:
        store.save(endpoint)
    with pytest.raises(EndpointError) as delete:
        store.delete(endpoint.id)
    assert all(
        error.value.code is EndpointFailureCode.FILE_INSECURE
        for error in (read, write, delete)
    )
    assert target.read_text(encoding="utf-8") == original


def test_removing_recorded_consent_blocks_both_engines_without_requests(
    tmp_path: Path, server: FakeServer
) -> None:
    configured = setup(tmp_path, server, key=KEY)
    file = tmp_path / ENDPOINTS_FILENAME
    document = json.loads(file.read_text(encoding="utf-8"))
    document["endpoints"][0].update(
        base_url="https://api.example.com/v1", cloud_consent=False
    )
    file.write_text(json.dumps(document), encoding="utf-8")

    assert configured.store.list() == ()
    for capability in (ModelCapability.TRANSCRIPTION, ModelCapability.SYNTHESIS):
        assert CompatibleModels(configured.store, capability).list_models() == ()
    with pytest.raises(SynthesisError) as speech:
        configured.speech().synthesize(
            "Hola",
            model=configured.descriptor(ModelCapability.SYNTHESIS),
            voice_id=VOICES[0],
        )
    with FIXTURE_WAV.open("rb") as audio, pytest.raises(TranscriptionError) as stt:
        configured.transcription().transcribe(
            audio=audio, options=configured.transcription_options()
        )
    assert speech.value.code is SynthesisFailureCode.MODEL_NOT_INSTALLED
    assert stt.value.code is TranscriptionFailureCode.MODEL_NOT_INSTALLED
    assert server.requests == []


# --- speech -------------------------------------------------------------------


def test_speech_sends_the_key_only_in_the_header(
    tmp_path: Path, server: FakeServer, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    configured = setup(tmp_path, server, key=KEY)
    provider = configured.speech()

    audio = provider.synthesize(
        "Hola",
        model=configured.descriptor(ModelCapability.SYNTHESIS),
        voice_id=VOICES[1],
        speed=1.25,
    )

    method, path, headers, body = server.requests[-1]
    assert (method, path) == ("POST", "/v1/audio/speech")
    assert headers["authorization"] == f"Bearer {KEY}"
    assert json.loads(body) == {
        "model": TTS_MODEL,
        "input": "Hola",
        "voice": VOICES[1],
        "response_format": "wav",
        "speed": 1.25,
    }
    assert audio.sample_rate == SAMPLE_RATE
    assert KEY not in repr(provider) and KEY not in caplog.text


def test_speech_errors_never_carry_the_key(tmp_path: Path, server: FakeServer) -> None:
    configured = setup(tmp_path, server, key="sk-wrong-key-1234")
    model = configured.descriptor(ModelCapability.SYNTHESIS)

    with pytest.raises(SynthesisError) as raised:
        configured.speech().synthesize("Hola", model=model, voice_id=VOICES[0])
    assert raised.value.code is SynthesisFailureCode.SYNTHESIS_FAILED
    assert not raised.value.retryable
    assert "sk-wrong" not in str(raised.value) and "401" not in str(raised.value)

    configured.secrets.set(configured.endpoint.secret_id, KEY)
    server.speech_status = 503
    with pytest.raises(SynthesisError) as raised:
        configured.speech().synthesize("Hola", model=model, voice_id=VOICES[0])
    assert raised.value.retryable and KEY not in str(raised.value)


def test_an_unreachable_server_is_runtime_unavailable(tmp_path: Path) -> None:
    dead = FakeServer("http://127.0.0.1:9")
    configured = setup(tmp_path, dead)

    with pytest.raises(SynthesisError) as raised:
        configured.speech().synthesize(
            "Hola",
            model=configured.descriptor(ModelCapability.SYNTHESIS),
            voice_id=VOICES[0],
        )
    assert raised.value.code is SynthesisFailureCode.RUNTIME_UNAVAILABLE
    assert raised.value.retryable


def test_cancellation_cuts_the_request_in_flight(
    tmp_path: Path, server: FakeServer
) -> None:
    configured = setup(tmp_path, server, key=KEY)
    server.speech_delay_s = 3.0
    started = time.monotonic()

    with pytest.raises(SynthesisError) as raised:
        configured.speech().synthesize(
            "Hola",
            model=configured.descriptor(ModelCapability.SYNTHESIS),
            voice_id=VOICES[0],
            cancellation=_CancelLater(0.2),
        )

    assert raised.value.code is SynthesisFailureCode.CANCELLED
    assert time.monotonic() - started < 2.0


def test_abort_does_not_depend_on_the_socket_waking_up(
    server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    # On Windows a local shutdown() does not wake a socket blocked in recv.
    def no_shutdown(self: socket.socket, how: int) -> None: ...

    monkeypatch.setattr(socket.socket, "shutdown", no_shutdown)
    server.speech_delay_s = 3.0
    deadline = time.monotonic() + 0.2
    started = time.monotonic()

    with pytest.raises(TransportError) as raised:
        urllib_transport(
            HttpRequest(
                f"{server.url}/v1/audio/speech",
                {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
                b'{"model": "kokoro", "input": "Hola"}',
                timeout_s=10.0,
                abort=lambda: time.monotonic() >= deadline,
            )
        )

    assert raised.value.aborted
    assert time.monotonic() - started < 2.0


def test_edits_apply_live_and_never_move_a_model_to_the_cloud(
    tmp_path: Path, server: FakeServer
) -> None:
    configured = setup(tmp_path, server, key=KEY)
    provider = configured.speech()
    model = configured.descriptor(ModelCapability.SYNTHESIS)
    assert provider.voices(model)

    configured.store.save(
        endpoint_for(
            server,
            base_url="https://api.example.com/v1",
            cloud_consent=True,
        )
    )
    with pytest.raises(SynthesisError) as raised:
        provider.synthesize("Hola", model=model, voice_id=VOICES[0])
    assert raised.value.code is SynthesisFailureCode.MODEL_NOT_INSTALLED
    assert len(server.requests) == 0  # nothing was sent anywhere

    cloud = CompatibleModels(configured.store, ModelCapability.SYNTHESIS).list_models()
    assert [item.descriptor.provider_id for item in cloud] == [CLOUD_PROVIDER_ID]
    assert cloud[0].cloud and cloud[0].provider_label == "Local test server"

    configured.store.delete(configured.endpoint.id)
    with pytest.raises(SynthesisError) as raised:
        provider.voices(model)
    assert raised.value.code is SynthesisFailureCode.MODEL_NOT_INSTALLED


def _wav(fmt_tag: int, bits: int, channels: int, data: bytes) -> bytes:
    fmt = struct.pack(
        "<HHIIHH", fmt_tag, channels, 16_000, 16_000 * channels * bits // 8, 1, bits
    )
    return (
        b"RIFF\x00\x00\x00\x00WAVE"
        + b"LIST"
        + struct.pack("<I", 3)
        + b"abc\x00"  # odd-sized chunk with its pad byte
        + b"fmt "
        + struct.pack("<I", len(fmt))
        + fmt
        + b"data"
        + struct.pack("<I", len(data))
        + data
    )


def test_decode_speech_handles_wav_variants_and_raw_pcm() -> None:
    streamed = decode_speech(wav_bytes(100, streaming=True), "audio/wav")
    assert (streamed.frame_count, streamed.sample_rate) == (100, SAMPLE_RATE)

    stereo = decode_speech(_wav(1, 16, 2, struct.pack("<hhhh", 1, 9, 2, 9)), "")
    assert stereo.samples == struct.pack("<hh", 1, 2)

    floats = decode_speech(_wav(3, 32, 1, struct.pack("<ff", 0.5, -0.5)), "")
    assert floats.sample_format is PcmSampleFormat.FLOAT32

    raw = decode_speech(b"\x01\x00\x02\x00\x03", "audio/pcm")
    assert (raw.frame_count, raw.sample_rate) == (2, 24_000)

    for bad in (b"ID3 mp3 bytes", _wav(1, 8, 1, b"\x01\x02"), _wav(1, 16, 1, b"")):
        with pytest.raises(SynthesisError):
            decode_speech(bad, "audio/mpeg")


def test_decode_speech_rejects_truncated_fmt_with_typed_error() -> None:
    truncated = b"RIFF\x00\x00\x00\x00WAVEfmt " + struct.pack("<I", 16) + b"\x01\x00"
    with pytest.raises(SynthesisError) as raised:
        decode_speech(truncated, "audio/wav")
    assert raised.value.code is SynthesisFailureCode.SYNTHESIS_FAILED


# --- transcription -------------------------------------------------------------


def test_transcription_without_key_sends_no_authorization(tmp_path: Path) -> None:
    with fake_server() as open_server:
        configured = setup(tmp_path, open_server)
        with FIXTURE_WAV.open("rb") as audio:
            result = configured.transcription().transcribe(
                audio=audio, options=configured.transcription_options()
            )
    method, path, headers, body = open_server.requests[-1]
    assert (method, path) == ("POST", "/v1/audio/transcriptions")
    assert "authorization" not in headers
    assert b'name="model"\r\n\r\nwhisper-tiny\r\n' in body
    assert result.text == "hola mundo"


def test_transcription_rejected_key_is_typed_and_redacted(
    tmp_path: Path, server: FakeServer
) -> None:
    configured = setup(tmp_path, server, key="sk-wrong-key-1234")
    with FIXTURE_WAV.open("rb") as audio, pytest.raises(TranscriptionError) as raised:
        configured.transcription().transcribe(
            audio=audio, options=configured.transcription_options()
        )
    assert "sk-wrong" not in str(raised.value)
    assert "OpenAI-compatible server rejected the API key" in str(raised.value)


def test_transcription_key_stays_in_header_and_out_of_logs(
    tmp_path: Path, server: FakeServer, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    configured = setup(tmp_path, server, key=KEY)
    provider = configured.transcription()
    with FIXTURE_WAV.open("rb") as audio:
        result = provider.transcribe(
            audio=audio, options=configured.transcription_options()
        )
    _, path, headers, body = server.requests[-1]
    assert headers["authorization"] == f"Bearer {KEY}"
    assert KEY not in path and KEY.encode() not in body
    assert KEY not in repr(provider) and KEY not in repr(result)
    assert KEY not in caplog.text


# --- connection test ------------------------------------------------------------


def test_connection_tester_reports_models_auth_and_unreachable(
    server: FakeServer,
) -> None:
    # Windows retries a refused loopback connect for about two seconds, so a
    # tight timeout would report endpoint_timeout instead of endpoint_unreachable.
    tester = HttpConnectionTester(urllib_transport, timeout_s=10.0)
    endpoint = endpoint_for(server)

    ok = tester.check(endpoint, KEY)
    assert (ok.reachable, ok.status, ok.models) == (
        True,
        200,
        ("whisper-tiny", TTS_MODEL),
    )
    assert server.requests[-1][:2] == ("GET", "/v1/models")

    rejected = tester.check(endpoint, "sk-wrong")
    assert (rejected.reachable, rejected.code) == (True, "endpoint_auth_rejected")

    gone = tester.check(endpoint_for(FakeServer("http://127.0.0.1:9")), None)
    assert (gone.reachable, gone.code) == (False, "endpoint_unreachable")


# --- default wiring through create_app ------------------------------------------


def _client(tmp_path: Path) -> TestClient:
    for name in ("data", "state"):
        (tmp_path / name).mkdir(exist_ok=True)
    paths = VozPaths(
        tmp_path / "config", tmp_path / "data", tmp_path / "cache", tmp_path / "state"
    )
    return TestClient(create_app(paths=paths))


def _body(server: FakeServer, **changes: object) -> dict[str, object]:
    return {
        "name": "Kokoro local",
        "base_url": server.base_url,
        "key": KEY,
        "stt_models": ["whisper-tiny"],
        "tts_models": [TTS_MODEL],
        "tts_voices": list(VOICES),
        **changes,
    }


def _wait_completed(client: httpx.Client, job_id: str) -> dict[str, object]:
    for _ in range(200):
        job = cast(dict[str, object], client.get(f"/api/synthesis/{job_id}").json())
        if job["state"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return job
        time.sleep(0.02)
    raise AssertionError("synthesis did not finish")


def test_default_app_lists_synthesizes_edits_and_deletes_live(
    tmp_path: Path, server: FakeServer, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    with _client(tmp_path) as test_client:
        client = cast(httpx.Client, test_client)
        created = client.post("/api/providers/compatible", json=_body(server))
        assert created.status_code == 201
        endpoint = created.json()
        assert endpoint["cloud"] is False and endpoint["key_configured"] is True
        assert KEY not in created.text

        tested = client.post(f"/api/providers/compatible/{endpoint['id']}/test")
        assert tested.json()["models"] == ["whisper-tiny", TTS_MODEL]

        stt = [
            option
            for option in client.get("/api/transcription-options").json()["options"]
            if option["provider_id"] == LOCAL_PROVIDER_ID
        ]
        assert len(stt) == 1
        assert stt[0]["can_start"] is True and stt[0]["cloud"] is False

        options = client.get("/api/synthesis/options").json()
        model = next(
            m for m in options["models"] if m["provider_id"] == LOCAL_PROVIDER_ID
        )
        assert [voice["id"] for voice in model["voices"]] == list(VOICES)
        job = client.post(
            "/api/synthesis",
            json={
                "text": "Hola desde un servidor compatible.",
                "provider_id": LOCAL_PROVIDER_ID,
                "model_id": model["model_id"],
                "voice_id": VOICES[0],
            },
        ).json()
        assert _wait_completed(client, job["id"])["state"] == "COMPLETED"
        audio = client.get(f"/api/synthesis/{job['id']}/audio")
        assert audio.status_code == 200 and audio.content[:4] == b"RIFF"

        # Editing without a key keeps it; dropping TTS removes it live.
        edited = client.put(
            f"/api/providers/compatible/{endpoint['id']}",
            json=_body(server, key=None, tts_models=[], tts_voices=[]),
        )
        assert edited.status_code == 200 and edited.json()["key_configured"] is True
        options = client.get("/api/synthesis/options").json()
        assert all(m["provider_id"] != LOCAL_PROVIDER_ID for m in options["models"])

        listed = client.get("/api/providers/compatible")
        assert KEY not in listed.text and "secret" not in listed.text

        url = f"/api/providers/compatible/{endpoint['id']}"
        assert client.delete(url).status_code == 403
        deleted = client.delete(
            url, headers={"X-VOZ-Action": "delete-compatible-endpoint"}
        )
        assert deleted.status_code == 204
        assert client.get("/api/providers/compatible").json() == []
        assert (
            client.delete(
                url, headers={"X-VOZ-Action": "delete-compatible-endpoint"}
            ).json()["detail"]["code"]
            == "endpoint_not_found"
        )
    secrets_file = tmp_path / "config" / "secrets.toml"
    assert not secrets_file.exists() or KEY not in secrets_file.read_text("utf-8")
    assert KEY not in caplog.text


def test_default_app_requires_consent_for_a_cloud_endpoint(tmp_path: Path) -> None:
    remote = FakeServer("https://api.example.com")
    with _client(tmp_path) as test_client:
        client = cast(httpx.Client, test_client)
        refused = client.post("/api/providers/compatible", json=_body(remote))
        assert refused.status_code == 422
        assert refused.json()["detail"]["code"] == "endpoint_cloud_consent_required"
        assert client.get("/api/providers/compatible").json() == []
        # The rejected request stored no key either.
        assert not (tmp_path / "config" / "secrets.toml").exists()

        accepted = client.post(
            "/api/providers/compatible", json=_body(remote, cloud_consent=True)
        ).json()
        assert accepted["cloud"] is True and accepted["cloud_consent"] is True
        stt = [
            option
            for option in client.get("/api/transcription-options").json()["options"]
            if option["provider_id"] == CLOUD_PROVIDER_ID
        ]
        assert stt[0]["cloud"] is True
        assert stt[0]["provider_label"] == "Kokoro local"
        assert stt[0]["recommendation"] is None
        providers = client.get("/api/synthesis/options").json()["providers"]
        assert {"provider_id": CLOUD_PROVIDER_ID, "locality": "cloud"}.items() <= next(
            p for p in providers if p["provider_id"] == CLOUD_PROVIDER_ID
        ).items()

        # Changing the URL needs consent again: it is never carried over.
        again = client.put(
            f"/api/providers/compatible/{accepted['id']}",
            json=_body(FakeServer("https://other.example.com")),
        )
        assert again.json()["detail"]["code"] == "endpoint_cloud_consent_required"


@pytest.mark.parametrize("method", ["post", "put"])
@pytest.mark.parametrize(
    "changes",
    [
        {"key": KEY * 80},
        {"key": {"token": KEY}},
        {"name": {"token": KEY}},
        {"base_url": {"token": KEY}},
    ],
    ids=["long-key", "object-key", "invalid-name", "invalid-url"],
)
def test_validation_errors_never_echo_secrets(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    method: str,
    changes: dict[str, object],
) -> None:
    caplog.set_level(logging.DEBUG)
    local = FakeServer("http://127.0.0.1:8000")
    with _client(tmp_path) as test_client:
        client = cast(httpx.Client, test_client)
        url = "/api/providers/compatible"
        if method == "put":
            created = client.post(url, json=_body(local))
            assert created.status_code == 201
            url += "/" + created.json()["id"]
        response = client.request(method, url, json=_body(local, **changes))
        assert response.status_code == 422
        assert KEY not in caplog.text
        assert KEY not in response.text
        detail = response.json()["detail"]
        assert isinstance(detail, dict)
        assert isinstance(detail["code"], str)
        assert isinstance(detail["message"], str)


def test_threads_do_not_leak(server: FakeServer, tmp_path: Path) -> None:
    before = threading.active_count()
    configured = setup(tmp_path, server, key=KEY)
    for _ in range(3):
        configured.speech().synthesize(
            "Hola",
            model=configured.descriptor(ModelCapability.SYNTHESIS),
            voice_id=VOICES[0],
        )
    assert threading.active_count() <= before + 1
