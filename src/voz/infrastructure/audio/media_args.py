"""How FFmpeg/ffprobe receive an already opened file, per platform.

VOZ opens originals and derivatives itself (no symlinks, exact identity) and
hands the open descriptor to the tool instead of a path wherever it can:

* ``proc``: Linux, ``/proc/self/fd/N`` plus an inherited descriptor.
* ``fd``: other POSIX (macOS), FFmpeg's ``-fd N fd:`` protocol plus an
  inherited descriptor.
* ``path``: Windows cannot inherit CRT descriptors through ``subprocess``, so
  the path of the open file is read back from its handle. The handle stays open
  (without delete sharing), so the file cannot be renamed or removed meanwhile.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Literal

Mode = Literal["proc", "fd", "path"]

# Tests set this to "fd" or "path" to exercise those modes on Linux.
FORCE_MODE: Mode | None = None

# Windows only: no console window flashes when VOZ launches the tools.
NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def mode() -> Mode:
    if FORCE_MODE is not None:
        return FORCE_MODE
    if os.name == "nt":
        return "path"
    return "proc" if os.path.isdir("/proc/self/fd") else "fd"


def path_of_descriptor(descriptor: int) -> str:
    """Current path of the file behind an open ``descriptor``.

    Windows: ``GetFinalPathNameByHandleW``. Linux: ``/proc/self/fd``. macOS:
    ``fcntl(F_GETPATH)``. Production only needs it on Windows; the other branches
    let tests exercise the ``path`` mode and inspect descriptors portably.
    """
    if sys.platform == "linux":
        return os.readlink(f"/proc/self/fd/{descriptor}")
    if sys.platform == "darwin":
        import fcntl

        raw = fcntl.fcntl(descriptor, fcntl.F_GETPATH, b"\0" * 1024)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        return os.fsdecode(bytes(raw).split(b"\0", 1)[0])  # pyright: ignore[reportUnknownArgumentType]
    if sys.platform != "win32":
        raise OSError("descriptor paths are not available on this platform")
    import ctypes
    import msvcrt
    from ctypes import wintypes

    function = ctypes.WinDLL("kernel32", use_last_error=True).GetFinalPathNameByHandleW
    function.argtypes = [
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    function.restype = wintypes.DWORD
    size = 32768
    buffer = ctypes.create_unicode_buffer(size)
    length = function(msvcrt.get_osfhandle(descriptor), buffer, size, 0)
    if length == 0 or length >= size:
        raise ctypes.WinError(ctypes.get_last_error())
    path = buffer.value
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[8:]
    return path.removeprefix("\\\\?\\")


def ffmpeg_input_arguments(descriptor: int) -> tuple[list[str], tuple[int, ...]]:
    """FFmpeg input arguments for an open file, and the fds to inherit.

    ``-fd N`` is a protocol option, so it precedes the URL it applies to.
    """
    selected = mode()
    if selected == "fd":
        return ["-fd", str(descriptor), "-i", "fd:"], (descriptor,)
    url, inherited = _url_for(selected, descriptor)
    return ["-i", url], inherited


def ffmpeg_output_arguments(descriptor: int) -> tuple[list[str], tuple[int, ...]]:
    """FFmpeg output arguments (last on the command line) for an open file."""
    selected = mode()
    if selected == "fd":
        return ["-fd", str(descriptor), "fd:"], (descriptor,)
    url, inherited = _url_for(selected, descriptor)
    return [url], inherited


def _url_for(selected: Mode, descriptor: int) -> tuple[str, tuple[int, ...]]:
    if selected == "proc":
        return f"/proc/self/fd/{descriptor}", (descriptor,)
    return path_of_descriptor(descriptor), ()


def ffprobe_file_arguments(descriptor: int) -> tuple[list[str], tuple[int, ...]]:
    """ffprobe input arguments for an open seekable file, and fds to inherit."""
    if mode() == "path":
        return [path_of_descriptor(descriptor)], ()
    return ["-fd", str(descriptor), "fd:"], (descriptor,)


__all__ = [
    "FORCE_MODE",
    "NO_WINDOW",
    "ffmpeg_input_arguments",
    "ffmpeg_output_arguments",
    "ffprobe_file_arguments",
    "mode",
    "path_of_descriptor",
]
