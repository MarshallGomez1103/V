"""Best-effort GPU/RAM measurement; any failure means "not measured" (None)."""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from voz.infrastructure.child_env import child_environment

_NVIDIA_SMI = (
    "nvidia-smi",
    "--query-gpu=name,memory.total,memory.free",
    "--format=csv,noheader,nounits",
)
_TIMEOUT_SECONDS = 5.0
_MAX_NAME = 120

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


@dataclass(frozen=True, slots=True)
class GpuMemory:
    name: str
    total_mib: int
    free_mib: int


@dataclass(frozen=True, slots=True)
class SystemMemory:
    total_mib: int
    available_mib: int


def read_gpu_memory(run: Runner = subprocess.run) -> GpuMemory | None:
    """First GPU reported by nvidia-smi (no shell); missing tool or failure -> None."""
    try:
        completed = run(
            list(_NVIDIA_SMI),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
            env=child_environment(),
        )
        if completed.returncode != 0:
            return None
        line = completed.stdout.strip().splitlines()[0]
        # rsplit keeps a comma inside the marketing name from shifting the numbers.
        name, total, free = (part.strip() for part in line.rsplit(",", 2))
        name = "".join(char for char in name if char.isprintable())[:_MAX_NAME]
        gpu = GpuMemory(name, int(total), int(free))
    except (OSError, subprocess.SubprocessError, IndexError, ValueError):
        return None
    if not gpu.name or gpu.total_mib <= 0 or not 0 <= gpu.free_mib <= gpu.total_mib:
        return None
    return gpu


def read_system_memory(
    path: Path = Path("/proc/meminfo"),
    platform: str = sys.platform,
    run: Runner = subprocess.run,
) -> SystemMemory | None:
    """RAM total/available; ``None`` whenever the platform cannot tell.

    Linux reads ``/proc/meminfo``, macOS asks ``sysctl``/``vm_stat`` and Windows
    calls ``GlobalMemoryStatusEx``; all stdlib, no extra dependency.
    """
    try:
        if platform.startswith("linux"):
            memory = _linux_memory(path)
        elif platform == "darwin":
            memory = _macos_memory(run)
        elif platform == "win32":
            memory = _windows_memory()
        else:
            return None
    except (OSError, KeyError, IndexError, ValueError, subprocess.SubprocessError):
        return None
    if (
        memory is None
        or memory.total_mib <= 0
        or memory.available_mib > memory.total_mib
    ):
        return None
    return memory


def _linux_memory(path: Path) -> SystemMemory:
    values: dict[str, int] = {}
    for line in path.read_text(encoding="ascii", errors="replace").splitlines():
        key, _, rest = line.partition(":")
        if key in {"MemTotal", "MemAvailable"}:
            values[key] = int(rest.split()[0]) // 1024  # kB -> MiB
    return SystemMemory(values["MemTotal"], values["MemAvailable"])


_VM_STAT_PAGE_SIZE = re.compile(r"page size of (\d+) bytes")
_VM_STAT_COUNTED = ("Pages free", "Pages inactive", "Pages speculative")


def _macos_memory(run: Runner) -> SystemMemory:
    total = run(
        ["sysctl", "-n", "hw.memsize"],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=True,
        env=child_environment(),
    ).stdout
    stats = run(
        ["vm_stat"],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=True,
        env=child_environment(),
    ).stdout
    header = _VM_STAT_PAGE_SIZE.search(stats.splitlines()[0])
    if header is None:
        raise ValueError("unrecognised vm_stat output")
    page_size = int(header.group(1))
    pages = 0
    for line in stats.splitlines()[1:]:
        key, _, rest = line.partition(":")
        if key in _VM_STAT_COUNTED:
            pages += int(rest.strip().rstrip("."))
    mib = 1024 * 1024
    return SystemMemory(int(total.strip()) // mib, pages * page_size // mib)


def _windows_memory() -> SystemMemory | None:
    if sys.platform != "win32":
        return None
    import ctypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = (
            ("length", ctypes.c_ulong),
            ("load", ctypes.c_ulong),
            ("total_phys", ctypes.c_ulonglong),
            ("avail_phys", ctypes.c_ulonglong),
            ("total_page", ctypes.c_ulonglong),
            ("avail_page", ctypes.c_ulonglong),
            ("total_virtual", ctypes.c_ulonglong),
            ("avail_virtual", ctypes.c_ulonglong),
            ("avail_extended", ctypes.c_ulonglong),
        )

    status = MemoryStatus()
    status.length = ctypes.sizeof(MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    mib = 1024 * 1024
    return SystemMemory(status.total_phys // mib, status.avail_phys // mib)


__all__ = [
    "GpuMemory",
    "SystemMemory",
    "read_gpu_memory",
    "read_system_memory",
]
