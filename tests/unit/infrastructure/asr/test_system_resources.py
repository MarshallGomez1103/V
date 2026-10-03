"""GPU/RAM measurement with fake subprocess and meminfo (no real nvidia-smi)."""

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from voz.infrastructure.asr.system_resources import (
    GpuMemory,
    read_gpu_memory,
    read_system_memory,
)


class FakeRun:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(
        self, args: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, self.returncode, self.stdout, "")


def fake_run(stdout: str = "", returncode: int = 0) -> FakeRun:
    return FakeRun(stdout, returncode)


def test_gpu_query_parses_first_gpu_without_shell_and_with_timeout() -> None:
    run = fake_run("NVIDIA GeForce RTX 4060 Laptop GPU, 8188, 7401\nOther, 1, 1\n")

    gpu = read_gpu_memory(run)

    assert gpu == GpuMemory("NVIDIA GeForce RTX 4060 Laptop GPU", 8188, 7401)
    args, kwargs = run.calls[0]
    assert args == [
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.free",
        "--format=csv,noheader,nounits",
    ]
    assert kwargs["timeout"] > 0
    assert not kwargs.get("shell")


def test_gpu_name_containing_a_comma_keeps_numbers_aligned() -> None:
    assert read_gpu_memory(fake_run("Some, Card, 4096, 100")) == GpuMemory(
        "Some, Card", 4096, 100
    )


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "garbage",
        "GPU, [N/A], [N/A]",
        "GPU, 100, 200",  # free > total is not credible
        "GPU, 0, 0",
        ", 100, 50",
    ],
)
def test_gpu_query_rejects_unusable_output(stdout: str) -> None:
    assert read_gpu_memory(fake_run(stdout)) is None


def test_gpu_query_nonzero_exit_is_none() -> None:
    assert read_gpu_memory(fake_run("GPU, 100, 50", returncode=9)) is None


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError("nvidia-smi"),
        PermissionError("denied"),
        subprocess.TimeoutExpired("nvidia-smi", 5),
        subprocess.SubprocessError("boom"),
    ],
)
def test_gpu_query_failures_are_none_never_exceptions(error: Exception) -> None:
    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise error

    assert read_gpu_memory(run) is None


def test_meminfo_reports_total_and_available_in_mib(tmp_path: Path) -> None:
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        "MemTotal:       65536000 kB\nMemFree:  100 kB\nMemAvailable:   32768000 kB\n"
    )

    memory = read_system_memory(meminfo, "linux")

    assert memory is not None
    assert memory.total_mib == 64000
    assert memory.available_mib == 32000


def test_meminfo_is_none_off_linux_missing_or_malformed(tmp_path: Path) -> None:
    good = tmp_path / "meminfo"
    good.write_text("MemTotal: 1024 kB\nMemAvailable: 512 kB\n")
    assert read_system_memory(good, "freebsd") is None
    assert read_system_memory(tmp_path / "missing", "linux") is None
    good.write_text("MemTotal: 1024 kB\n")
    assert read_system_memory(good, "linux") is None
    good.write_text("MemTotal: many kB\nMemAvailable: 1 kB\n")
    assert read_system_memory(good, "linux") is None


_VM_STAT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               10000.
Pages active:                            200000.
Pages inactive:                           30000.
Pages speculative:                         5000.
"""


class _MacRun:
    def __init__(self, memsize: str, vm_stat: str) -> None:
        self.outputs = {"sysctl": memsize, "vm_stat": vm_stat}

    def __call__(
        self, args: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, self.outputs[args[0]], "")


def test_macos_memory_comes_from_sysctl_and_vm_stat() -> None:
    run = _MacRun(str(16 * 1024**3) + "\n", _VM_STAT)

    memory = read_system_memory(Path("/nonexistent"), "darwin", run)

    assert memory is not None
    assert memory.total_mib == 16 * 1024
    assert memory.available_mib == (10000 + 30000 + 5000) * 16384 // 1024**2


def test_macos_memory_is_none_when_tools_fail_or_output_is_unexpected() -> None:
    def missing(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(args[0])

    assert read_system_memory(Path("/x"), "darwin", missing) is None
    garbage = _MacRun("lots\n", "no header here\n")
    assert read_system_memory(Path("/x"), "darwin", garbage) is None
    free_exceeds_total = _MacRun("1024\n", _VM_STAT)
    assert read_system_memory(Path("/x"), "darwin", free_exceeds_total) is None


def test_windows_memory_is_none_off_windows() -> None:
    # Real value is only measurable on Windows; elsewhere it must not raise.
    result = read_system_memory(Path("/x"), "win32")
    if sys.platform == "win32":
        assert result is not None and result.total_mib > 0
    else:
        assert result is None
