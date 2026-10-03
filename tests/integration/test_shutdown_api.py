"""``POST /api/shutdown``: header guard, 202 answer and the delayed stop."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import threading
from pathlib import Path

from fastapi.testclient import TestClient

from voz.bootstrap import create_app
from voz.infrastructure.paths import VozPaths

HEADER = {"X-VOZ-Action": "shutdown"}


def _paths(tmp_path: Path) -> VozPaths:
    return VozPaths(
        tmp_path / "config", tmp_path / "data", tmp_path / "cache", tmp_path / "state"
    )


def _client(tmp_path: Path, stop: threading.Event | None) -> TestClient:
    for path in (tmp_path / "data", tmp_path / "state"):
        path.mkdir()
    app = create_app(
        paths=_paths(tmp_path),
        request_shutdown=None if stop is None else stop.set,
    )
    return TestClient(app)


def test_shutdown_answers_202_and_stops_the_server_shortly_after(
    tmp_path: Path,
) -> None:
    stop = threading.Event()
    with _client(tmp_path, stop) as client:
        response = client.post("/api/shutdown", headers=HEADER)

        assert response.status_code == 202
        assert response.json() == {"status": "stopping"}
        assert not stop.is_set()  # the response goes out before the server stops
        assert stop.wait(5), "the server was never asked to stop"


def test_shutdown_without_the_action_header_is_forbidden(tmp_path: Path) -> None:
    stop = threading.Event()
    with _client(tmp_path, stop) as client:
        missing = client.post("/api/shutdown")
        wrong = client.post("/api/shutdown", headers={"X-VOZ-Action": "other"})

        for response in (missing, wrong):
            assert response.status_code == 403
            assert response.json()["detail"]["code"] == "shutdown_forbidden"
        assert not stop.wait(0.8)  # never scheduled


def test_shutdown_is_post_only(tmp_path: Path) -> None:
    stop = threading.Event()
    with _client(tmp_path, stop) as client:
        assert client.get("/api/shutdown", headers=HEADER).status_code in {404, 405}
        assert not stop.wait(0.8)


def test_server_not_started_by_the_cli_cannot_be_stopped_from_the_api(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, None) as client:
        response = client.post("/api/shutdown", headers=HEADER)

        assert response.status_code == 501
        assert response.json()["detail"]["code"] == "shutdown_unavailable"
