"""Best-effort GPU/RAM measurement; any failure means "not measured" (None)."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

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
    path: Path = Path("/proc/meminfo"), platform: str = sys.platform
) -> SystemMemory | None:
    """RAM total/available from ``/proc/meminfo`` (Linux only); otherwise None."""
    if not platform.startswith("linux"):
        return None
    try:
        values: dict[str, int] = {}
        for line in path.read_text(encoding="ascii", errors="replace").splitlines():
            key, _, rest = line.partition(":")
            if key in {"MemTotal", "MemAvailable"}:
                values[key] = int(rest.split()[0]) // 1024  # kB -> MiB
        memory = SystemMemory(values["MemTotal"], values["MemAvailable"])
    except (OSError, KeyError, IndexError, ValueError):
        return None
    if memory.total_mib <= 0 or memory.available_mib > memory.total_mib:
        return None
    return memory


__all__ = [
    "GpuMemory",
    "SystemMemory",
    "read_gpu_memory",
    "read_system_memory",
]
