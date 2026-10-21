"""Package smoke uses disposable state and owns only its process group."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "packaging/common/smoke.sh"
pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX smoke supervisor")
STATE_KEYS = (
    "HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
    "XDG_STATE_HOME",
    "XDG_RUNTIME_DIR",
)
SERVER = r"""
import argparse, json, os, signal, socketserver, subprocess, sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--no-browser", action="store_true")
parser.add_argument("--port", type=int)
args = parser.parse_args()
mode = os.environ["SMOKE_MODE"]
child = None
if mode in ("child", "child-crash"):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                             stdin=subprocess.DEVNULL)
Path(os.environ["SMOKE_RECORD"]).write_text(json.dumps({
    "env": {key: os.environ.get(key) for key in __STATE_KEYS__},
    "pid": os.getpid(), "child": child.pid if child else None,
    "cwd": os.getcwd(), "args": vars(args),
}))
if mode in ("crash", "child-crash"):
    sys.exit(9)
def stop(signum, frame):
    if child is not None:
        child.wait(timeout=1)
    raise SystemExit(7 if mode == "bad-stop" else 0)
signal.signal(signal.SIGINT, signal.SIG_IGN if mode == "ignore-stop" else stop)
if mode == "api-stop":
    signal.signal(signal.SIGINT, lambda *_: sys.exit(130))
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        action = self.headers.get("X-VOZ-Action")
        code = 202 if self.path == "/api/shutdown" and action == "shutdown" else 403
        if mode == "bad-shutdown":
            code = 500
        self.send_response(code)
        self.end_headers()
        if code != 202 or mode == "ignore-stop":
            return
        record = Path(os.environ["SMOKE_RECORD"])
        record.write_text(json.dumps({**json.loads(record.read_text()),
                                      "shutdown_header": action}))
        if child is not None:
            child.terminate()
            child.wait(timeout=1)
        raise SystemExit(7 if mode == "bad-stop" else 0)
    def do_GET(self):
        if mode == "stall":
            import time
            time.sleep(60)
        self.send_response(500 if mode == "bad-ui" and self.path == "/" else 200)
        self.end_headers()
    def log_message(self, *args):
        pass
# TCPServer, not HTTPServer: HTTPServer.server_bind does a reverse DNS lookup
# (socket.getfqdn), which can stall on macOS runners past the smoke deadline.
socketserver.TCPServer(("127.0.0.1", args.port), Handler).serve_forever()
""".replace("__STATE_KEYS__", repr(STATE_KEYS))


def run_smoke(
    tmp_path: Path, mode: str, deadline: float = 0.8
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    server = tmp_path / "fake V server.py"
    server.write_text(SERVER)
    record = tmp_path / "record.json"
    host = tmp_path / "host"
    host.mkdir()
    marker = host / "keep"
    marker.write_text("untouched")
    env = {
        **os.environ,
        **{key: str(host) for key in STATE_KEYS},
        "SMOKE_RECORD": str(record),
        "SMOKE_MODE": mode,
        "VOZ_SMOKE_TIMEOUT": str(deadline),
    }
    result = subprocess.run(
        ["bash", str(SMOKE), sys.executable, str(server)],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=deadline + 5,
    )
    assert marker.read_text() == "untouched"
    assert list(host.iterdir()) == [marker]
    state = json.loads(record.read_text())
    try:
        os.kill(state["pid"], 0)
    except ProcessLookupError:
        pass
    else:
        os.killpg(state["pid"], signal.SIGKILL)
        pytest.fail("smoke left its server alive")
    return result, state


def test_smoke_isolates_home_xdg_cwd_and_stops_its_child(tmp_path: Path) -> None:
    # A ready server ends the smoke at once; the margin only covers slow runners.
    result, state = run_smoke(tmp_path, "child", deadline=10)
    assert result.returncode == 0, result.stderr
    assert "clean shutdown" in result.stdout
    assert state["args"]["no_browser"] is True
    for key in STATE_KEYS:
        assert state["env"][key] != str(tmp_path / "host")
        assert not Path(state["env"][key]).exists()
    assert not Path(state["cwd"]).exists()
    with pytest.raises(ProcessLookupError):
        os.kill(state["child"], 0)


def test_smoke_uses_api_shutdown_instead_of_sigint(tmp_path: Path) -> None:
    result, state = run_smoke(tmp_path, "api-stop", deadline=10)
    assert result.returncode == 0, result.stderr
    assert state["shutdown_header"] == "shutdown"
    assert "clean shutdown" in result.stdout


@pytest.mark.parametrize(
    "mode", ["crash", "stall", "bad-ui", "bad-stop", "ignore-stop", "bad-shutdown"]
)
def test_smoke_fails_and_cleans_up_with_real_deadlines(
    tmp_path: Path, mode: str
) -> None:
    started = time.monotonic()
    result, _ = run_smoke(tmp_path, mode)
    assert result.returncode != 0
    assert "clean shutdown" not in result.stdout
    assert time.monotonic() - started < 4


@pytest.mark.skipif(sys.platform != "linux", reason="Linux child-state inspection")
def test_cleanup_reaches_children_after_leader_exits_and_leaves_other_groups(
    tmp_path: Path,
) -> None:
    other = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        result, state = run_smoke(tmp_path, "child-crash")
        assert result.returncode != 0
        assert other.poll() is None
        status = Path(f"/proc/{state['child']}/stat")
        # An orphan can remain a zombie until the host init reaps it.
        deadline = time.monotonic() + 1
        while status.exists():
            if status.read_text().split(")", 1)[1].split()[0] in ("Z", "X"):
                break
            assert time.monotonic() < deadline, "smoke left its orphan child alive"
            time.sleep(0.01)
    finally:
        other.terminate()
        other.wait(timeout=2)


@pytest.mark.parametrize("command", ["flatpak", "/usr/bin/flatpak"])
def test_flatpak_is_rejected_before_launch(tmp_path: Path, command: str) -> None:
    result = subprocess.run(
        ["bash", str(SMOKE), command, "run", "dev.example.V"],
        env={**os.environ, "HOME": str(tmp_path)},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert result.returncode != 0
    assert "Flatpak smoke requires verified sandbox isolation" in result.stderr
