"""``/api/synthesis`` through the real app with the fake TTS engine (V3-05)."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import io
import json
import time
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
)
from voz.bootstrap import create_app
from voz.domain.entities.synthesis_request import MAX_SYNTHESIS_TEXT_CHARS
from voz.infrastructure.paths import VozPaths
from voz.infrastructure.tts.fake import (
    FAKE_TTS_PROVIDER_ID,
    FakeSpeechSynthesisProvider,
    fake_tts_descriptor,
)

DELETE = {"X-VOZ-Action": "delete-synthesis"}


class _Catalog:
    def __init__(self, *, installed: bool = True) -> None:
        self._installed = installed

    def list_models(self) -> tuple[ModelRegistration, ...]:
        return (
            ModelRegistration(
                fake_tts_descriptor(),
                InstallationStatus.REGISTERED
                if self._installed
                else InstallationStatus.NOT_REGISTERED,
                files_available=self._installed,
            ),
        )


def _body(**overrides: object) -> dict[str, object]:
    return {
        "text": "Hello there. This is V speaking.",
        "provider_id": FAKE_TTS_PROVIDER_ID,
        "model_id": "tone",
        "voice_id": "tone-low",
        **overrides,
    }


def _app_client(tmp_path: Path, *, installed: bool = True) -> TestClient:
    for name in ("data", "state"):
        (tmp_path / name).mkdir(exist_ok=True)
    paths = VozPaths(
        tmp_path / "config", tmp_path / "data", tmp_path / "cache", tmp_path / "state"
    )
    return TestClient(
        create_app(
            paths=paths,
            synthesis_providers=[FakeSpeechSynthesisProvider(max_chunk_chars=20)],
            synthesis_catalog=_Catalog(installed=installed),
        )
    )


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with _app_client(tmp_path) as test_client:
        yield test_client


def _wait_terminal(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        view = client.get(f"/api/synthesis/{job_id}").json()
        if view["state"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return view
        time.sleep(0.02)
    raise AssertionError("the synthesis job never finished")


def _sse(body: str) -> list[tuple[str, Any]]:
    events: list[tuple[str, Any]] = []
    for block in body.split("\n\n"):
        if block and not block.startswith(":"):
            fields = dict(line.split(": ", 1) for line in block.split("\n"))
            events.append((fields["event"], json.loads(fields["data"])))
    return events


def _assert_no_host_paths(payload: object, tmp_path: Path) -> None:
    text = json.dumps(payload)
    assert str(tmp_path) not in text
    assert "/home/" not in text and "audio.wav" not in text


def test_options_list_the_fake_engine_model_voices_and_limits(
    client: TestClient, tmp_path: Path
) -> None:
    response = client.get("/api/synthesis/options")

    assert response.status_code == 200
    options = response.json()
    assert options["providers"] == [
        {
            "provider_id": "fake-tts",
            "display_name": "Fake TTS (test tone)",
            "locality": "local",
        }
    ]
    (model,) = options["models"]
    assert model["model_id"] == "tone" and model["runtime_ready"] is True
    assert model["languages"] == ["en", "es"]
    assert [voice["id"] for voice in model["voices"]] == [
        "tone-low",
        "tone-high",
        "silence",
    ]
    assert options["max_chars"] == MAX_SYNTHESIS_TEXT_CHARS
    assert options["speed"] == {"min": 0.5, "max": 2.0}
    _assert_no_host_paths(options, tmp_path)


def test_options_hide_models_that_are_not_installed(tmp_path: Path) -> None:
    with _app_client(tmp_path, installed=False) as client:
        options = client.get("/api/synthesis/options").json()
        assert options["models"] == []

        response = client.post("/api/synthesis", json=_body())
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "synthesis_model_not_installed"


def test_default_app_has_no_synthesis_engines(tmp_path: Path) -> None:
    for name in ("data", "state"):
        (tmp_path / name).mkdir()
    paths = VozPaths(
        tmp_path / "config", tmp_path / "data", tmp_path / "cache", tmp_path / "state"
    )
    with TestClient(create_app(paths=paths)) as client:
        options = client.get("/api/synthesis/options").json()
        assert options["providers"] == [] and options["models"] == []
        response = client.post("/api/synthesis", json=_body())
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "synthesis_provider_not_found"


def test_full_flow_create_events_audio_history_delete(
    client: TestClient, tmp_path: Path
) -> None:
    created = client.post("/api/synthesis", json=_body())
    assert created.status_code == 201
    job = created.json()
    assert job["reused"] is False and job["state"] in {"QUEUED", "RUNNING"}
    assert job["chunks_total"] == 2  # two sentences under the 20-char engine cap

    events = _sse(client.get(f"/api/synthesis/{job['id']}/events").text)
    assert events[-1] == ("end", {})
    last = events[-2][1]
    assert last["state"] == "COMPLETED" and last["progress"] == 1.0

    view = client.get(f"/api/synthesis/{job['id']}").json()
    assert view["text"] == "Hello there. This is V speaking."
    audio = view["audio"]
    assert audio["url"] == f"/api/synthesis/{job['id']}/audio"
    assert audio["sample_rate"] == 16_000 and audio["duration_ms"] > 0

    full = client.get(audio["url"])
    assert full.status_code == 200
    assert full.headers["content-type"] == "audio/wav"
    assert full.headers["accept-ranges"] == "bytes"
    assert (
        int(full.headers["content-length"]) == audio["size_bytes"] == len(full.content)
    )
    disposition = full.headers["content-disposition"]
    assert disposition.startswith('inline; filename="v-')
    assert disposition.endswith('-tone-low.wav"')
    with wave.open(io.BytesIO(full.content)) as reader:
        assert reader.getframerate() == 16_000 and reader.getnchannels() == 1

    part = client.get(audio["url"], headers={"Range": "bytes=0-3"})
    assert part.status_code == 206
    assert part.content == b"RIFF"
    assert part.headers["content-range"] == f"bytes 0-3/{audio['size_bytes']}"
    tail = client.get(audio["url"], headers={"Range": "bytes=-4"})
    assert tail.status_code == 206 and tail.content == full.content[-4:]
    beyond = client.get(
        audio["url"], headers={"Range": f"bytes={audio['size_bytes'] + 10}-"}
    )
    assert beyond.status_code == 416
    assert beyond.headers["content-range"] == f"bytes */{audio['size_bytes']}"
    attachment = client.get(audio["url"], params={"download": "true"})
    assert attachment.headers["content-disposition"].startswith("attachment;")

    history = client.get("/api/synthesis", params={"limit": 10}).json()["items"]
    assert [item["id"] for item in history] == [job["id"]]
    assert history[0]["audio"]["size_bytes"] == audio["size_bytes"]
    assert "text" not in history[0]

    for payload in (job, events, view, history):
        _assert_no_host_paths(payload, tmp_path)

    deleted = client.delete(f"/api/synthesis/{job['id']}", headers=DELETE)
    assert deleted.status_code == 204
    assert client.get(f"/api/synthesis/{job['id']}").status_code == 404
    assert client.get(audio["url"]).status_code == 404
    assert not (tmp_path / "data" / "synthesis" / job["id"]).exists()
    assert client.get("/api/synthesis").json() == {"items": []}


def test_identical_request_reuses_the_completed_result(client: TestClient) -> None:
    first = client.post("/api/synthesis", json=_body()).json()
    _wait_terminal(client, first["id"])

    again = client.post("/api/synthesis", json=_body())

    assert again.status_code == 200
    reused = again.json()
    assert reused["reused"] is True and reused["id"] == first["id"]
    assert reused["state"] == "COMPLETED" and reused["audio"] is not None
    other_voice = client.post("/api/synthesis", json=_body(voice_id="tone-high"))
    assert other_voice.status_code == 201


def test_cancel_a_long_job_then_delete_it(client: TestClient) -> None:
    long_text = " ".join(["This sentence keeps the tone going."] * 200)
    job = client.post("/api/synthesis", json=_body(text=long_text)).json()

    cancelled = client.post(f"/api/synthesis/{job['id']}/cancel")

    assert cancelled.status_code == 202
    assert cancelled.json()["state"] in {"CANCELLING", "CANCELLED"}
    final = _wait_terminal(client, job["id"])
    assert final["state"] == "CANCELLED" and final["audio"] is None
    again = client.post(f"/api/synthesis/{job['id']}/cancel")
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "synthesis_job_terminal"
    audio = client.get(f"/api/synthesis/{job['id']}/audio")
    assert audio.status_code == 409
    assert audio.json()["detail"]["code"] == "synthesis_audio_not_ready"
    assert (
        client.delete(f"/api/synthesis/{job['id']}", headers=DELETE).status_code == 204
    )


def test_delete_requires_the_action_header_and_a_finished_job(
    client: TestClient,
) -> None:
    long_text = " ".join(["Another long sentence for the queue."] * 200)
    job = client.post("/api/synthesis", json=_body(text=long_text)).json()

    for headers in ({}, {"X-VOZ-Action": "other"}):
        forbidden = client.delete(f"/api/synthesis/{job['id']}", headers=headers)
        assert forbidden.status_code == 403
        assert forbidden.json()["detail"]["code"] == "synthesis_delete_forbidden"
    active = client.delete(f"/api/synthesis/{job['id']}", headers=DELETE)
    assert active.status_code == 409
    assert active.json()["detail"]["code"] == "synthesis_job_active"

    client.post(f"/api/synthesis/{job['id']}/cancel")
    _wait_terminal(client, job["id"])


@pytest.mark.parametrize(
    ("overrides", "status", "code"),
    [
        ({"provider_id": "nope"}, 404, "synthesis_provider_not_found"),
        ({"model_id": "nope"}, 404, "synthesis_model_unknown"),
        ({"voice_id": "nope"}, 404, "synthesis_voice_not_found"),
        ({"text": "   "}, 422, "synthesis_request_invalid"),
        (
            {"text": "a" * (MAX_SYNTHESIS_TEXT_CHARS + 1)},
            422,
            "synthesis_request_invalid",
        ),
        ({"speed": 5.0}, 422, "synthesis_request_invalid"),
    ],
)
def test_create_errors_are_typed(
    client: TestClient,
    tmp_path: Path,
    overrides: dict[str, object],
    status: int,
    code: str,
) -> None:
    response = client.post("/api/synthesis", json=_body(**overrides))

    assert response.status_code == status
    detail = response.json()["detail"]
    assert detail["code"] == code and detail["message"]
    _assert_no_host_paths(detail, tmp_path)


def test_unknown_jobs_answer_404(client: TestClient) -> None:
    missing = "00000000-0000-4000-8000-000000000000"
    for method, path in (
        ("GET", f"/api/synthesis/{missing}"),
        ("GET", f"/api/synthesis/{missing}/events"),
        ("GET", f"/api/synthesis/{missing}/audio"),
        ("POST", f"/api/synthesis/{missing}/cancel"),
        ("DELETE", f"/api/synthesis/{missing}"),
    ):
        response = client.request(method, path, headers=DELETE)
        assert response.status_code == 404, path
        assert response.json()["detail"]["code"] == "synthesis_job_not_found"


def test_host_guard_still_applies(client: TestClient) -> None:
    response = client.get(
        "/api/synthesis/options", headers={"Host": "evil.example:8000"}
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "host_not_allowed"
