"""``kill_tree`` ends the child and, on Windows, whatever it started."""

from __future__ import annotations

import os
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


@pytest.mark.skipif(os.name != "nt", reason="POSIX ends trees by process group")
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
