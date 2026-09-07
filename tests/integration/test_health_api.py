"""Integration test for the health endpoint over a real loopback socket."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import cast

from voz import __version__


def _available_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        return cast(int, server_socket.getsockname()[1])


def _fetch_health(url: str, *, timeout: float = 10.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                return cast(dict[str, object], json.load(response))
        except (OSError, TimeoutError, urllib.error.URLError):
            time.sleep(0.05)
    raise AssertionError(f"VOZ did not become ready at {url}")


def _fetch_home(url: str) -> str:
    with urllib.request.urlopen(url, timeout=1.0) as response:
        return response.read().decode()


def test_health_endpoint_reports_readiness_without_sensitive_paths(
    tmp_path: Path,
) -> None:
    port = _available_loopback_port()
    environment = os.environ.copy()
    environment["PYTHONPYCACHEPREFIX"] = str(tmp_path / "pycache")
    environment["XDG_DATA_HOME"] = str(tmp_path / "data")
    environment["XDG_CACHE_HOME"] = str(tmp_path / "cache")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "voz.bootstrap:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        payload = _fetch_health(f"http://127.0.0.1:{port}/api/health")
        home = _fetch_home(f"http://127.0.0.1:{port}/")
        options = _fetch_health(f"http://127.0.0.1:{port}/api/transcription-options")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    assert payload == {"status": "ok", "version": __version__}
    assert not any("path" in key.lower() for key in payload)
    assert '<div id="root"></div>' in home
    assert "VOZ" in home
    choices = cast(list[dict[str, object]], options["options"])
    assert {item["model_id"] for item in choices} == {"turbo", "large-v3"}
    assert all(item["can_start"] is False for item in choices)
    assert str(tmp_path) not in json.dumps(options)
