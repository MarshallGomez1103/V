"""End a child together with its descendants on Windows.

A virtualenv's ``python.exe`` there is a launcher whose real interpreter is its
child: killing only the launcher lets the interpreter outlive it for a moment,
still holding the child's inherited pipes and files open.
"""

from __future__ import annotations

import contextlib
import os
import subprocess

_NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def kill_tree(child: subprocess.Popen[bytes]) -> None:
    """Kill ``child`` and its descendants and reap it; a no-op once it has exited."""
    if child.poll() is not None:
        return
    if os.name == "nt":
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(child.pid)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_NO_WINDOW,
                timeout=5,
                check=False,
            )
    child.kill()
    child.wait()
