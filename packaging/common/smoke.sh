#!/usr/bin/env bash
# Smoke a V package with disposable HOME/XDG state and a bounded shutdown.
# Usage: packaging/common/smoke.sh ./V.AppImage [arguments...]
# Flatpak is refused until sandbox state and instance cleanup are verified.
set -euo pipefail
exec python3 - "$@" <<'PY'
import math
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

command = sys.argv[1:]
def interrupted(signum, frame):
    raise KeyboardInterrupt
signal.signal(signal.SIGTERM, interrupted)
if not command:
    sys.exit("Usage: packaging/common/smoke.sh <command...>")
if Path(command[0]).name == "flatpak":
    sys.exit("Flatpak smoke requires verified sandbox isolation; not launched.")
try:
    timeout = float(os.environ.get("VOZ_SMOKE_TIMEOUT", "30"))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError
except ValueError:
    sys.exit("VOZ_SMOKE_TIMEOUT must be a positive finite number.")

# ponytail: one local process group; Flatpak needs separate sandbox supervision.
with tempfile.TemporaryDirectory(prefix="v-smoke-") as work:
    env = os.environ.copy()
    for key, directory in {
        "HOME": "home", "XDG_CONFIG_HOME": "config", "XDG_DATA_HOME": "data",
        "XDG_CACHE_HOME": "cache", "XDG_STATE_HOME": "state",
        "XDG_RUNTIME_DIR": "runtime",
    }.items():
        path = Path(work, directory)
        path.mkdir(mode=0o700)
        env[key] = str(path)
    cwd = Path(work, "cwd")
    cwd.mkdir()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    # Resolve relative executable paths before entering the disposable cwd.
    if "/" in command[0]:
        command[0] = str(Path(command[0]).resolve())
    with Path(work, "server.log").open("w+") as log:
        process = subprocess.Popen(
            [*command, "--no-browser", "--port", str(port)], env=env, cwd=cwd,
            stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
        )
        try:
            started = time.monotonic()
            deadline = started + timeout
            # Ignore host proxy settings for the loopback probe.
            http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for route in ("/api/health", "/"):
                while True:
                    remaining = deadline - time.monotonic()
                    if process.poll() is not None:
                        raise RuntimeError("Server exited before smoke completed.")
                    if remaining <= 0:
                        raise RuntimeError(f"{route} did not respond 200 before deadline.")
                    try:
                        with http.open(f"http://127.0.0.1:{port}{route}",
                                       timeout=min(0.2, remaining)) as response:
                            if response.status == 200:
                                break
                    except (OSError, urllib.error.URLError):
                        pass
                    time.sleep(min(0.05, max(0, deadline - time.monotonic())))
            print(f"ok  /api/health and / 200 in {time.monotonic() - started:.2f} s")
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/shutdown", method="POST",
                headers={"X-VOZ-Action": "shutdown"},
            )
            with http.open(request, timeout=min(timeout, 5)) as response:
                if response.status != 202:
                    raise RuntimeError("Server did not accept shutdown (expected 202).")
            if process.wait(timeout=min(timeout, 5)) != 0:
                raise RuntimeError("Server shutdown returned a nonzero exit code.")
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                pass
            else:
                raise RuntimeError("Server shutdown left child processes alive.")
            print("ok  clean shutdown (exit 0)")
        except (OSError, RuntimeError, subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            print(f"Smoke failed: {error}", file=sys.stderr)
            sys.exit(1)
        finally:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(process.pid, sig)
                except ProcessLookupError:
                    break
                try:
                    process.wait(timeout=min(timeout, 1))
                except subprocess.TimeoutExpired:
                    pass
            process.wait(timeout=1)
PY
