"""One server per data directory: the lock dies with its holder."""

from __future__ import annotations

import errno
import os
import stat
import subprocess
import sys
import types
from pathlib import Path

import pytest

from voz.infrastructure import instance_lock
from voz.infrastructure.instance_lock import InstanceLock, InstanceLockError

_HOLDER = (
    "import sys\n"
    "from pathlib import Path\n"
    "from voz.infrastructure.instance_lock import InstanceLock\n"
    "InstanceLock(Path(sys.argv[1])).acquire()\n"
    "print('held', flush=True)\n"
    "sys.stdin.read()\n"
)


def test_a_second_holder_is_refused_until_the_first_releases(tmp_path: Path) -> None:
    path = tmp_path / "state" / "instance.lock"
    first, second = InstanceLock(path), InstanceLock(path)
    first.acquire()

    with pytest.raises(InstanceLockError) as refused:
        second.acquire()
    assert refused.value.code == "instance_already_running"
    assert str(tmp_path) not in str(refused.value)

    first.release()
    second.acquire()
    second.release()


def test_release_is_idempotent_and_a_never_acquired_lock_releases_quietly(
    tmp_path: Path,
) -> None:
    lock = InstanceLock(tmp_path / "instance.lock")

    lock.release()
    lock.acquire()
    lock.release()
    lock.release()


def test_a_lock_that_cannot_be_created_is_reported_without_the_path(
    tmp_path: Path,
) -> None:
    blocker = tmp_path / "state"
    blocker.write_text("a file where the directory should be")

    with pytest.raises(InstanceLockError) as failed:
        InstanceLock(blocker / "instance.lock").acquire()

    assert failed.value.code == "instance_lock_unavailable"
    assert str(tmp_path) not in str(failed.value)


@pytest.mark.skipif(os.name == "nt", reason="needs POSIX SIGKILL semantics")
def test_the_lock_is_freed_when_its_holder_is_killed(tmp_path: Path) -> None:
    path = tmp_path / "instance.lock"
    holder = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "held"
        with pytest.raises(InstanceLockError):
            InstanceLock(path).acquire()
        holder.kill()
        holder.wait()

        survivor = InstanceLock(path)
        survivor.acquire()
        survivor.release()
    finally:
        holder.kill()
        holder.wait()
        for stream in (holder.stdin, holder.stdout):
            if stream is not None:
                stream.close()


@pytest.mark.parametrize("busy", [errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES])
def test_only_a_busy_errno_means_another_server_is_running(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, busy: int
) -> None:
    def taken(_descriptor: int) -> None:
        raise OSError(busy, "busy")

    monkeypatch.setattr(instance_lock, "_lock", taken)

    with pytest.raises(InstanceLockError) as refused:
        InstanceLock(tmp_path / "instance.lock").acquire()

    assert refused.value.code == "instance_already_running"


@pytest.mark.parametrize("failure", [errno.ENOLCK, errno.EIO, errno.EBADF])
def test_any_other_lock_failure_is_not_blamed_on_another_server(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: int
) -> None:
    def broken(_descriptor: int) -> None:
        raise OSError(failure, "broken")

    monkeypatch.setattr(instance_lock, "_lock", broken)

    with pytest.raises(InstanceLockError) as failed:
        InstanceLock(tmp_path / "instance.lock").acquire()

    assert failed.value.code == "instance_lock_unavailable"
    assert str(tmp_path) not in str(failed.value)


def test_windows_unlocks_the_region_before_closing_the_handle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, int]] = []

    def locking(descriptor: int, mode: int, length: int) -> None:
        del descriptor
        calls.append(("lock" if mode == 1 else "unlock", length))
        if mode == 0:
            raise OSError(errno.EACCES, "already unlocked")  # release must shrug it off

    fake = types.SimpleNamespace(LK_UNLCK=0, LK_NBLCK=1, locking=locking)
    monkeypatch.setitem(sys.modules, "msvcrt", fake)
    monkeypatch.setattr(sys, "platform", "win32")
    lock = InstanceLock(tmp_path / "instance.lock")

    lock.acquire()
    lock.release()

    assert calls == [("lock", 1), ("unlock", 1)]


@pytest.mark.skipif(os.name == "nt", reason="POSIX modes and flock")
def test_lock_file_is_private_and_not_inherited_by_children(tmp_path: Path) -> None:
    path = tmp_path / "state" / "instance.lock"
    probe = (
        "import fcntl, sys\n"
        "with open(sys.argv[1], 'rb') as handle:\n"
        "    try:\n"
        "        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
        "    except OSError as error:\n"
        "        print(error.errno)\n"
        "    else:\n"
        "        print('free')\n"
    )

    def probed() -> str:
        return subprocess.run(
            [sys.executable, "-c", probe, str(path)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    lock = InstanceLock(path)
    lock.acquire()
    sleeper = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"], close_fds=False
    )
    try:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert probed() == str(errno.EWOULDBLOCK)

        lock.release()

        # A child started while the lock was held would keep it alive if it had
        # inherited the descriptor.
        assert probed() == "free"
    finally:
        sleeper.kill()
        sleeper.wait()
