"""``/api/desktop-shortcut`` through the real app with a temporary home."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from voz.application.ports.desktop_shortcut import DesktopShortcutError
from voz.interfaces.api.desktop_shortcut import create_desktop_shortcut_router

HEADER = {"X-VOZ-Action": "desktop-shortcut"}


class _Shortcut:
    def __init__(self, *, supported: bool = True, fail: bool = False) -> None:
        self._supported = supported
        self._fail = fail
        self.created = 0
        self._where: str | None = None

    def supported(self) -> bool:
        return self._supported

    def exists(self) -> bool:
        return self._where is not None

    def location(self) -> str | None:
        return self._where

    def create(self) -> str:
        if self._fail:
            raise DesktopShortcutError("/home/secret/path failed")
        self.created += 1
        self._where = "~/Desktop/voz.desktop"
        return self._where


def _client(shortcut: _Shortcut) -> TestClient:
    app = FastAPI()
    app.include_router(create_desktop_shortcut_router(shortcut))
    return TestClient(app)


def test_get_reports_support_and_existence() -> None:
    shortcut = _Shortcut()
    client = _client(shortcut)

    assert client.get("/api/desktop-shortcut").json() == {
        "supported": True,
        "exists": False,
        "path": None,
    }

    assert client.post("/api/desktop-shortcut", headers=HEADER).status_code == 201

    assert client.get("/api/desktop-shortcut").json() == {
        "supported": True,
        "exists": True,
        "path": "~/Desktop/voz.desktop",
    }


def test_post_creates_and_recreates() -> None:
    shortcut = _Shortcut()
    client = _client(shortcut)

    first = client.post("/api/desktop-shortcut", headers=HEADER)
    second = client.post("/api/desktop-shortcut", headers=HEADER)

    assert first.status_code == second.status_code == 201
    assert first.json() == {
        "supported": True,
        "exists": True,
        "path": "~/Desktop/voz.desktop",
    }
    assert shortcut.created == 2


@pytest.mark.parametrize("headers", [{}, {"X-VOZ-Action": "shutdown"}])
def test_post_requires_the_action_header(headers: dict[str, str]) -> None:
    shortcut = _Shortcut()

    response = _client(shortcut).post("/api/desktop-shortcut", headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "desktop_shortcut_forbidden"
    assert shortcut.created == 0


def test_unsupported_install_reports_it_and_refuses_to_create() -> None:
    shortcut = _Shortcut(supported=False)
    client = _client(shortcut)

    assert client.get("/api/desktop-shortcut").json() == {
        "supported": False,
        "exists": False,
        "path": None,
    }
    response = client.post("/api/desktop-shortcut", headers=HEADER)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "desktop_shortcut_unsupported"
    assert shortcut.created == 0


def test_failure_is_a_500_without_host_paths() -> None:
    response = _client(_Shortcut(fail=True)).post(
        "/api/desktop-shortcut", headers=HEADER
    )

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "desktop_shortcut_failed"
    assert "/home" not in response.text


def test_the_composed_app_serves_it(tmp_path: Path) -> None:
    from voz.bootstrap import create_app
    from voz.infrastructure.paths import VozPaths

    paths = VozPaths(tmp_path / "c", tmp_path / "d", tmp_path / "ca", tmp_path / "s")
    for path in (paths.data, paths.state):
        path.mkdir()
    with TestClient(create_app(paths=paths)) as client:
        body = client.get("/api/desktop-shortcut").json()

    assert set(body) == {"supported", "exists", "path"}
    assert body["exists"] is False  # nothing was created in the temp state dir
