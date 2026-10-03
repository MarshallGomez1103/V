"""Directory-relative file operations with a portable fallback.

On Linux and macOS a directory chain is opened without following symlinks and
every later operation is relative to the directory descriptor (``*at`` calls),
so a concurrent path swap cannot redirect it. Windows has neither ``dir_fd`` nor
directories as descriptors: there the same operations run on checked paths.

ponytail: the portable path re-validates each component with ``lstat`` before
use but cannot close the check/use window like ``dir_fd`` does. Windows is a
single-user desktop target and the storage roots live in the user's profile, so
this is accepted instead of an NT-handle implementation through ctypes.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path

# Windows opens descriptors in text mode unless told otherwise.
BINARY_FLAG = getattr(os, "O_BINARY", 0)

# Tests flip this to exercise the portable branch on a POSIX machine.
FORCE_PORTABLE = False


class DirectoryDurabilityError(OSError):
    """A freshly created directory entry could not be flushed to disk."""


# Computed once: tests wrap ``os.open``/``os.link`` and a wrapper is not a member
# of ``os.supports_dir_fd`` even though the real call is.
_NATIVE_DIR_FD = (
    os.name != "nt"
    and {os.open, os.mkdir, os.unlink, os.stat, os.link} <= os.supports_dir_fd
    and os.link in os.supports_follow_symlinks
)


def dir_fd_supported() -> bool:
    """Whether ``dir_fd``-relative operations (and directory fds) are available."""
    return _NATIVE_DIR_FD and not FORCE_PORTABLE


def fchmod(descriptor: int, mode: int) -> bool:
    """``os.fchmod`` where it exists (not on Windows before Python 3.13)."""
    if not hasattr(os, "fchmod"):
        return False
    os.fchmod(descriptor, mode)
    return True


def best_effort_chmod(path: Path, mode: int) -> None:
    """``chmod`` that never raises: Windows only honours the read-only bit."""
    with suppress(OSError):
        os.chmod(path, mode)


def is_link_like(path: Path, info: os.stat_result) -> bool:
    """Symlink, or an NTFS junction (``lstat`` reports those as directories)."""
    return stat.S_ISLNK(info.st_mode) or os.path.isjunction(path)


class DirectoryHandle:
    """A directory plus the operations that must stay inside it."""

    __slots__ = ("_fd", "path")

    def __init__(self, path: Path, fd: int | None) -> None:
        self.path = path
        self._fd = fd

    def open_file(self, name: str, flags: int, mode: int = 0o777) -> int:
        flags |= BINARY_FLAG
        if self._fd is not None:
            return os.open(name, flags, mode, dir_fd=self._fd)
        target = self.path / name
        # Without O_NOFOLLOW (Windows) a link must be refused explicitly.
        if not flags & os.O_CREAT and is_link_like(target, target.lstat()):
            raise OSError(f"{name} is a link")
        return os.open(target, flags, mode)

    def unlink(self, name: str) -> None:
        if self._fd is not None:
            os.unlink(name, dir_fd=self._fd)
            return
        target = self.path / name
        try:
            os.unlink(target)
        except PermissionError:
            if os.name != "nt":
                raise
            # Windows refuses to delete read-only files (our originals are).
            os.chmod(target, stat.S_IWRITE | stat.S_IREAD)
            os.unlink(target)

    def stat(self, name: str, *, follow_symlinks: bool = True) -> os.stat_result:
        if self._fd is not None:
            return os.stat(name, dir_fd=self._fd, follow_symlinks=follow_symlinks)
        return os.stat(self.path / name, follow_symlinks=follow_symlinks)

    def link(self, source: str, destination: str) -> None:
        """Hard-link ``source`` to ``destination``; never replaces an existing name."""
        if self._fd is not None:
            os.link(
                source,
                destination,
                src_dir_fd=self._fd,
                dst_dir_fd=self._fd,
                follow_symlinks=False,
            )
            return
        # ponytail: NTFS and POSIX filesystems hard-link; FAT/exFAT volumes fail
        # here with a clear IO error instead of silently copying.
        os.link(self.path / source, self.path / destination)

    def chmod(self, name: str, mode: int) -> None:
        os.chmod(self.path / name, mode)

    def fsync(self) -> None:
        if self._fd is not None:
            os.fsync(self._fd)
            return
        if os.name == "nt":
            return  # NTFS cannot fsync a directory; its journal covers renames.
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(self.path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)


def _directory_flags() -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    return flags | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def open_directory_chain(
    root: Path,
    components: Iterable[str],
    *,
    create: bool,
    durable: bool = False,
) -> DirectoryHandle:
    """Open ``root/<components...>`` refusing links; optionally create the chain.

    Raises ``FileNotFoundError`` for a missing directory and ``OSError`` when a
    component is a link, is not a directory or changed while being opened.
    ``durable`` flushes the parent after each created directory and raises
    ``DirectoryDurabilityError`` if that fails.
    """
    if create:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root_lstat = root.lstat()
    if is_link_like(root, root_lstat):
        raise OSError("storage root is a symbolic link")
    if not dir_fd_supported():
        return _open_chain_by_path(root, root_lstat, components, create, durable)

    flags = _directory_flags()
    current_fd = os.open(root, flags)
    try:
        root_fstat = os.fstat(current_fd)
        if not stat.S_ISDIR(root_fstat.st_mode) or not os.path.samestat(
            root_lstat, root_fstat
        ):
            raise OSError("storage root changed while it was being opened")
        current = root
        for component in components:
            if create:
                created = False
                try:
                    os.mkdir(component, mode=0o700, dir_fd=current_fd)
                    created = True
                except FileExistsError:
                    pass
                if created and durable:
                    try:
                        os.fsync(current_fd)
                    except OSError as error:
                        raise DirectoryDurabilityError(str(error)) from error
            next_fd = os.open(component, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
            current = current / component
    except BaseException:
        os.close(current_fd)
        raise
    return DirectoryHandle(current, current_fd)


def _open_chain_by_path(
    root: Path,
    root_lstat: os.stat_result,
    components: Iterable[str],
    create: bool,
    durable: bool,
) -> DirectoryHandle:
    if not stat.S_ISDIR(root_lstat.st_mode):
        raise OSError("storage root is not a directory")
    current = root
    for component in components:
        parent = DirectoryHandle(current, None)
        current = current / component
        if create:
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
            else:
                if durable:
                    try:
                        parent.fsync()
                    except OSError as error:
                        raise DirectoryDurabilityError(str(error)) from error
        info = current.lstat()
        if is_link_like(current, info) or not stat.S_ISDIR(info.st_mode):
            raise OSError(f"{component} is not a plain directory")
    return DirectoryHandle(current, None)
