"""Boot the real ``voz`` server in a subprocess and read its health endpoint.

Runs on every platform in CI: it proves the launcher entry point, migrations,
the per-platform data directories and the HTTP stack start together.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

_SERVE = "from voz.interfaces.cli.main import main; main()"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_server_starts_and_reports_healthy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for variable in ("DATA", "CONFIG", "CACHE", "STATE"):
        monkeypatch.setenv(f"XDG_{variable}_HOME", str(tmp_path / variable.lower()))
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-c", _SERVE, "--no-browser", "--port", str(port)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 90
        payload: object = None
        while time.monotonic() < deadline and payload is None:
            if process.poll() is not None:
                break
            try:
                url = f"http://127.0.0.1:{port}/api/health"
                with urllib.request.urlopen(url, timeout=2) as response:
                    payload = json.loads(response.read())
            except OSError:
                time.sleep(0.3)
        assert payload is not None, "the server never answered /api/health"
        assert isinstance(payload, dict)
        assert payload["status"] == "ok"  # pyright: ignore[reportUnknownVariableType]
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        if process.stderr is not None:
            process.stderr.close()
    assert (tmp_path / "data" / "voz").is_dir()
