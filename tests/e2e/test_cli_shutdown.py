"""The real ``voz`` server exits cleanly after ``POST /api/shutdown``."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_SERVE = "from voz.interfaces.cli.main import main; main()"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _post(url: str, headers: dict[str, str]) -> tuple[int, object]:
    request = urllib.request.Request(url, method="POST", headers=headers, data=b"")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_post_shutdown_terminates_the_real_server_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for variable in ("DATA", "CONFIG", "CACHE", "STATE"):
        monkeypatch.setenv(f"XDG_{variable}_HOME", str(tmp_path / variable.lower()))
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [sys.executable, "-c", _SERVE, "--no-browser", "--port", str(port)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            assert process.poll() is None, "the server died while starting"
            try:
                with urllib.request.urlopen(f"{base}/api/health", timeout=2):
                    break
            except OSError:
                time.sleep(0.3)
        else:
            pytest.fail("the server never answered /api/health")

        status, body = _post(f"{base}/api/shutdown", {})
        assert (status, body["detail"]["code"]) == (403, "shutdown_forbidden")  # type: ignore[index]
        assert process.poll() is None  # the forbidden call did not stop it

        status, body = _post(f"{base}/api/shutdown", {"X-VOZ-Action": "shutdown"})
        assert (status, body) == (202, {"status": "stopping"})

        assert process.wait(timeout=20) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
