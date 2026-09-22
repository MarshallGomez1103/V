"""Unit tests for ``voz doctor`` with every system dependency faked."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from voz.application.asr_device_selection import HardwareCapabilities
from voz.application.ports.transcription_options import (
    RuntimeAvailability,
    TranscriptionRuntimeProbe,
)
from voz.domain.entities.processing_profile import ComputePrecision
from voz.infrastructure.paths import VozPaths
from voz.interfaces.cli.doctor import (
    DoctorReport,
    HardwareProbe,
    Run,
    Which,
    exit_code,
    render,
    run_doctor,
)
from voz.interfaces.cli.main import app as cli_app

GIB = 1024**3


class FakeRuntimeProbe:
    def __init__(self, available: bool) -> None:
        self.available = available

    def probe(self, provider_id: str) -> RuntimeAvailability:
        assert provider_id == "faster-whisper"
        return RuntimeAvailability(self.available)


class FakeHardwareProbe:
    def __init__(self, cuda: frozenset[ComputePrecision]) -> None:
        self.cuda = cuda

    def probe(self) -> HardwareCapabilities:
        return HardwareCapabilities(
            cuda_compute_types=self.cuda,
            cpu_compute_types=frozenset({ComputePrecision.INT8}),
        )


class ExplodingHardwareProbe:
    def probe(self) -> HardwareCapabilities:
        raise RuntimeError("libcuda.so not found")


def fake_which(name: str) -> str | None:
    return f"/usr/bin/{name}"


def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
    tool = Path(command[0]).name
    return subprocess.CompletedProcess(
        command,
        0,
        stdout=f"{tool} version 6.1.1 Copyright (c) 2000-2024 the FFmpeg developers\n",
        stderr="",
    )


def tmp_paths(root: Path) -> VozPaths:
    return VozPaths(
        config=root / "config" / "voz",
        data=root / "data" / "voz",
        cache=root / "cache" / "voz",
        state=root / "state" / "voz",
    )


def healthy_report(
    tmp_path: Path,
    *,
    paths: VozPaths | None = None,
    redact: bool = False,
    which: Which = fake_which,
    run: Run = fake_run,
    port_in_use: Callable[[str, int], bool] = lambda _host, _port: False,
    free_bytes: Callable[[Path], int] = lambda _path: 10 * GIB,
    runtime_probe: TranscriptionRuntimeProbe | None = None,
    hardware_probe: HardwareProbe | None = None,
) -> DoctorReport:
    """Every dependency faked as healthy; override one to exercise a path."""
    return run_doctor(
        paths=paths or tmp_paths(tmp_path),
        redact=redact,
        which=which,
        run=run,
        port_in_use=port_in_use,
        free_bytes=free_bytes,
        runtime_probe=runtime_probe or FakeRuntimeProbe(True),
        hardware_probe=hardware_probe
        or FakeHardwareProbe(frozenset({ComputePrecision.FLOAT16})),
    )


def statuses(report: DoctorReport) -> dict[str, str]:
    return {check.name: check.status for check in report.checks}


def test_all_ok_exits_zero(tmp_path: Path) -> None:
    report = healthy_report(tmp_path)

    assert set(statuses(report).values()) == {"ok"}
    assert exit_code(report) == 0
    assert (tmp_path / "data" / "voz").is_dir()
    rendered = render(report)
    assert "ffmpeg version 6.1.1" in rendered
    assert "Copyright" not in rendered
    assert "Resumen: 7 ok, 0 avisos, 0 fallos." in rendered


def test_missing_ffmpeg_fails_and_exits_one(tmp_path: Path) -> None:
    report = healthy_report(
        tmp_path,
        which=lambda name: None if name == "ffmpeg" else f"/usr/bin/{name}",
    )

    assert statuses(report)["ffmpeg"] == "fail"
    assert statuses(report)["ffprobe"] == "ok"
    assert exit_code(report) == 1
    assert "[FALLO] ffmpeg" in render(report)


def test_tool_timeout_is_a_failure_without_traceback(tmp_path: Path) -> None:
    def slow_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, 5)

    report = healthy_report(tmp_path, run=slow_run)

    assert statuses(report)["ffmpeg"] == "fail"
    assert "TimeoutExpired" in report.checks[0].detail
    assert "Traceback" not in report.checks[0].detail


def test_busy_port_warns(tmp_path: Path) -> None:
    report = healthy_report(tmp_path, port_in_use=lambda _host, _port: True)

    port_check = next(check for check in report.checks if check.name == "puerto")
    assert port_check.status == "warn"
    assert "posiblemente VOZ ya está corriendo" in port_check.detail
    assert exit_code(report) == 0


def test_low_disk_space_warns(tmp_path: Path) -> None:
    report = healthy_report(tmp_path, free_bytes=lambda _path: GIB)

    assert statuses(report)["disco"] == "warn"


def test_unwritable_path_fails(tmp_path: Path) -> None:
    paths = tmp_paths(tmp_path)
    blocked = tmp_path / "config"
    blocked.write_text("not a directory")  # mkdir below it must fail

    report = healthy_report(tmp_path, paths=paths)

    assert statuses(report)["rutas"] == "fail"
    assert exit_code(report) == 1


def test_redact_hides_absolute_paths(tmp_path: Path) -> None:
    shown = healthy_report(tmp_path)
    hidden = healthy_report(tmp_path, redact=True)

    paths_shown = next(c for c in shown.checks if c.name == "rutas").detail
    paths_hidden = next(c for c in hidden.checks if c.name == "rutas").detail
    assert str(tmp_path) in paths_shown
    assert str(tmp_path) not in paths_hidden
    assert "rutas locales del usuario" in paths_hidden


def test_missing_runtime_warns(tmp_path: Path) -> None:
    report = healthy_report(tmp_path, runtime_probe=FakeRuntimeProbe(False))

    runtime = next(c for c in report.checks if c.name == "runtime ASR")
    assert runtime.status == "warn"
    assert "asr-local" in runtime.detail
    assert exit_code(report) == 0


def test_cpu_only_hardware_warns(tmp_path: Path) -> None:
    report = healthy_report(tmp_path, hardware_probe=FakeHardwareProbe(frozenset()))

    gpu = next(c for c in report.checks if c.name == "GPU/CUDA")
    assert gpu.status == "warn"
    assert gpu.detail == "solo CPU (int8)"


def test_gpu_probe_exception_warns_with_type_only(tmp_path: Path) -> None:
    report = healthy_report(tmp_path, hardware_probe=ExplodingHardwareProbe())

    gpu = next(c for c in report.checks if c.name == "GPU/CUDA")
    assert gpu.status == "warn"
    assert "RuntimeError" in gpu.detail
    assert "libcuda" not in gpu.detail
    assert "Traceback" not in gpu.detail
    assert exit_code(report) == 0


def test_cli_doctor_json_is_parseable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for variable in ("CONFIG", "DATA", "CACHE", "STATE"):
        monkeypatch.setenv(f"XDG_{variable}_HOME", str(tmp_path / variable.lower()))

    result = CliRunner().invoke(cli_app, ["doctor", "--json", "--port", "1"])

    assert result.exit_code in {0, 1}
    payload = json.loads(result.output)
    names = [check["name"] for check in payload["checks"]]
    assert names == [
        "ffmpeg",
        "ffprobe",
        "puerto",
        "rutas",
        "disco",
        "runtime ASR",
        "GPU/CUDA",
    ]
    assert all(check["status"] in {"ok", "warn", "fail"} for check in payload["checks"])
    assert (result.exit_code == 1) == any(
        check["status"] == "fail" for check in payload["checks"]
    )
