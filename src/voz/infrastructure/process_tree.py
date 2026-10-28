"""End a child together with its descendants.

Windows: a virtualenv's ``python.exe`` is a launcher whose real interpreter is
its child; killing only the launcher lets the interpreter outlive it for a
moment, still holding the child's inherited pipes and files open.

POSIX: the child must have been started with ``start_new_session=True``, so its
descendants share its process group and one signal to the group reaches them all.
This module is the only place that signals a process group.

Orphans: the group is signalled only by a live server. If the server dies
without cleaning up (SIGKILL, crash, power loss) nothing signals it, and a
session of its own also shields it from the terminal's Ctrl-C: the child and its
descendants run on, reparented to init, until they finish by themselves. Workers
are short-lived and carry their own timeouts, and no pdeathsig is installed.
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
        stop_group(child, grace)
        child.wait()
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


def stop_group(child: subprocess.Popen[bytes], grace: float = _GRACE_SECONDS) -> None:
    """End the group ``child`` leads: SIGTERM, up to ``grace`` seconds, then SIGKILL.

    Works while the leader lives and after it exited (the final SIGKILL still
    sweeps its descendants). ``grace <= 0`` skips SIGTERM. Does not reap
    ``child``; ``child`` must have been started with ``start_new_session=True``.
    """
    if grace > 0:
        _signal_group(child.pid, signal.SIGTERM)
        with contextlib.suppress(subprocess.TimeoutExpired):
            child.wait(timeout=grace)
    # Sweep what ignored SIGTERM, even if the leader is already gone.
    _signal_group(child.pid, signal.SIGKILL)


def _signal_group(pgid: int, sig: int) -> None:
    # macOS may answer EPERM for a group whose only member is an unreaped zombie.
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pgid, sig)
