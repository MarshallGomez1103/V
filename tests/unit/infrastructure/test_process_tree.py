"""``kill_tree`` ends the child and whatever it started."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from voz.infrastructure.process_tree import kill_tree

_SLEEP = "import time; time.sleep(30)"


def test_kill_tree_ends_a_running_child_and_ignores_a_finished_one() -> None:
    child = subprocess.Popen([sys.executable, "-c", _SLEEP])

    kill_tree(child)
    kill_tree(child)

    assert child.poll() is not None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _grandchild_script(pid_file: Path) -> str:
    return (
        "import subprocess, sys, time\n"
        f"g = subprocess.Popen([sys.executable, '-c', {_SLEEP!r}])\n"
        f"open({str(pid_file)!r}, 'w').write(str(g.pid))\n"
        "time.sleep(30)\n"
    )


def _wait_for(path: Path) -> int:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if path.exists() and path.read_text():
            return int(path.read_text())
        time.sleep(0.05)
    pytest.fail("the child never published its grandchild")


@pytest.mark.skipif(os.name == "nt", reason="POSIX ends trees by process group")
def test_kill_tree_takes_the_grandchild_too_on_posix(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    child = subprocess.Popen(
        [sys.executable, "-c", _grandchild_script(pid_file)], start_new_session=True
    )
    grandchild = _wait_for(pid_file)

    kill_tree(child)

    deadline = time.monotonic() + 5
    while _alive(grandchild) and time.monotonic() < deadline:
        time.sleep(0.05)
    try:
        assert not _alive(grandchild), "the grandchild outlived kill_tree"
    finally:
        if _alive(grandchild):
            os.kill(grandchild, signal.SIGKILL)


@pytest.mark.skipif(os.name == "nt", reason="POSIX ends trees by process group")
def test_kill_tree_never_signals_the_servers_own_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[int, int]] = []

    def killpg(pgid: int, sig: int) -> None:
        sent.append((pgid, sig))

    monkeypatch.setattr(os, "killpg", killpg)
    child = subprocess.Popen([sys.executable, "-c", _SLEEP])  # same group as us

    kill_tree(child)

    assert sent == []
    assert child.poll() is not None


@pytest.mark.skipif(os.name != "nt", reason="Windows ends trees with taskkill /T")
def test_kill_tree_takes_the_grandchild_too(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    script = (
        "import subprocess, sys, time\n"
        f"g = subprocess.Popen([sys.executable, '-c', {_SLEEP!r}])\n"
        f"open({str(pid_file)!r}, 'w').write(str(g.pid))\n"
        "time.sleep(30)\n"
    )
    child = subprocess.Popen([sys.executable, "-c", script])
    deadline = time.monotonic() + 15
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    grandchild = int(pid_file.read_text())

    kill_tree(child)

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        probe = subprocess.run(
            ["tasklist", "/FI", f"PID eq {grandchild}", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        if str(grandchild) not in probe.stdout:
            return
        time.sleep(0.1)
    pytest.fail("the grandchild outlived kill_tree")


_CANCELLABLE_SPAWNERS = (
    "asr/sherpa_onnx.py",
    "asr/whisper_cpp.py",
    "constrained_process.py",
    "custom_model_worker.py",
    "diarization/sherpa.py",
    "tts/subprocess_provider.py",
)


@pytest.mark.parametrize("module", _CANCELLABLE_SPAWNERS)
def test_every_cancellable_spawn_gets_its_own_session(module: str) -> None:
    import ast

    root = Path(__file__).parents[3] / "src" / "voz" / "infrastructure"
    tree = ast.parse((root / module).read_text(encoding="utf-8"))
    spawns = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute | ast.Name)
        and (getattr(node.func, "attr", None) or getattr(node.func, "id", None))
        in ("Popen", "_popen")
    ]

    assert spawns, module
    for spawn in spawns:
        assert "start_new_session" in {k.arg for k in spawn.keywords}, spawn.lineno
