"""Host header guard: DNS rebinding cannot reach the loopback API (ADR-0006)."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from voz.bootstrap import create_app
from voz.infrastructure.paths import VozPaths
from voz.infrastructure.server_token import create_server_token


def _client(tmp_path: Path, allowed_hosts: tuple[str, ...] = ()) -> TestClient:
    paths = VozPaths(
        tmp_path / "config", tmp_path / "data", tmp_path / "cache", tmp_path / "state"
    )
    for path in (paths.data, paths.state):
        path.mkdir(parents=True)
    return TestClient(create_app(paths=paths, allowed_hosts=allowed_hosts))


@pytest.mark.parametrize(
    "path",
    ["/api/health", f"/api/jobs/{uuid4()}/events", "/", "/assets/missing.js"],
)
def test_foreign_host_is_rejected_on_api_sse_and_static(
    tmp_path: Path, path: str
) -> None:
    with _client(tmp_path) as client:
        response = client.get(path, headers={"Host": "evil.example"})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "host_not_allowed"
    assert "evil.example" not in response.text


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "127.0.0.1:8765", "localhost:5173", "LOCALHOST", "[::1]:8765"],
)
def test_loopback_hosts_on_any_port_are_allowed(tmp_path: Path, host: str) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/health", headers={"Host": host})

    assert response.status_code == 200


@pytest.mark.parametrize(
    "host", ["127.0.0.1.evil.example", "localhost.evil.example", "[::1", ""]
)
def test_lookalike_or_malformed_hosts_are_rejected(tmp_path: Path, host: str) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/health", headers={"Host": host})

    assert response.status_code == 400


def test_explicit_bind_host_is_allowed_but_not_others(tmp_path: Path) -> None:
    with _client(tmp_path, allowed_hosts=("192.168.1.20",)) as client:
        lan = client.get("/api/health", headers={"Host": "192.168.1.20:8765"})
        loopback = client.get("/api/health", headers={"Host": "localhost"})
        other = client.get("/api/health", headers={"Host": "192.168.1.21"})

    assert (lan.status_code, loopback.status_code, other.status_code) == (
        200,
        200,
        400,
    )


def test_testserver_is_not_in_the_production_allowlist(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        default = client.get("/api/health")  # conftest points it at 127.0.0.1
        testserver = client.get("/api/health", headers={"Host": "testserver"})

    assert (default.status_code, testserver.status_code) == (200, 400)


def test_cli_passes_the_bind_host_to_the_guard(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from voz.interfaces.cli import main

    seen: dict[str, object] = {}

    def fake_create_app(**kwargs: object) -> object:
        seen.update(kwargs)
        return object()

    class FakeServer:
        def __init__(self, config: object) -> None: ...

        def run(self) -> None: ...

    monkeypatch.setattr(main, "is_server_ready", lambda _url, **_kwargs: False)
    monkeypatch.setattr(main, "create_app", fake_create_app)
    monkeypatch.setattr(main.uvicorn, "Server", FakeServer)

    token_file = tmp_path / "token"
    create_server_token(token_file)
    main.run_server(
        host="192.168.1.20", port=8765, open_browser=False, auth_token_file=token_file
    )

    assert seen["allowed_hosts"] == ("192.168.1.20",)
