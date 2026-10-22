"""End a child together with its descendants.

Windows: a virtualenv's ``python.exe`` is a launcher whose real interpreter is
its child; killing only the launcher lets the interpreter outlive it for a
moment, still holding the child's inherited pipes and files open.

POSIX: the child must have been started with ``start_new_session=True``, so its
descendants share its process group and one signal to the group reaches them all.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess

from voz.infrastructure.child_env import child_environment

_NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_GRACE_SECONDS: float = 2.0


def kill_tree(child: subprocess.Popen[bytes], grace: float = _GRACE_SECONDS) -> None:
    """Kill ``child`` and its descendants and reap it; a no-op once it has exited."""
    if child.poll() is not None:
        return
    if os.name != "nt" and _owns_group(child):
        _stop_group(child, grace)
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
                env=child_environment(),
            )
    child.kill()
    child.wait()


def _owns_group(child: subprocess.Popen[bytes]) -> bool:
    """True when ``child`` leads a group of its own, never the server's."""
    try:
        return os.getpgid(child.pid) != os.getpgid(0)
    except ProcessLookupError:
        return False


def _stop_group(child: subprocess.Popen[bytes], grace: float) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(child.pid, signal.SIGTERM)
    with contextlib.suppress(subprocess.TimeoutExpired):
        child.wait(timeout=grace)
    # Sweep what ignored SIGTERM, even if the leader is already gone. macOS may
    # answer EPERM for a group whose only member is an unreaped zombie.
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(child.pid, signal.SIGKILL)
    child.wait()
