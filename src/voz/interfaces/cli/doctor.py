"""Pure diagnostics behind ``voz doctor``: no model downloads, no engine loads."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from voz.application.asr_device_selection import HardwareCapabilities
from voz.application.ports.transcription_options import TranscriptionRuntimeProbe
from voz.infrastructure.asr.hardware import CTranslate2HardwareProbe
from voz.infrastructure.asr.options import FasterWhisperRuntimeProbe
from voz.infrastructure.paths import VozPaths, resolve_voz_paths

Status = Literal["ok", "warn", "fail"]
Which = Callable[[str], str | None]
Run = Callable[[list[str]], "subprocess.CompletedProcess[str]"]

VERSION_TIMEOUT_SECONDS = 5.0
MIN_FREE_BYTES = 2 * 1024**3
_STATUS_LABEL: dict[Status, str] = {"ok": "OK", "warn": "AVISO", "fail": "FALLO"}


class HardwareProbe(Protocol):
    def probe(self) -> HardwareCapabilities: ...


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    status: Status
    detail: str


@dataclass(frozen=True, slots=True)
class DoctorReport:
    checks: tuple[DoctorCheck, ...]

    @property
    def has_failures(self) -> bool:
        return any(check.status == "fail" for check in self.checks)


def _run_version(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
        errors="replace",
        timeout=VERSION_TIMEOUT_SECONDS,
    )


def _port_in_use(host: str, port: int) -> bool:
    family = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)[0][0]
    try:
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            probe.bind((host, port))
    except OSError:
        return True
    return False


def _free_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


def _check_tool(name: str, which: Which, run: Run) -> DoctorCheck:
    executable = which(name)
    if executable is None:
        return DoctorCheck(name, "fail", "no encontrado en PATH; instala FFmpeg")
    try:
        completed = run([executable, "-version"])
    except (OSError, subprocess.TimeoutExpired) as error:
        return DoctorCheck(
            name, "fail", f"no se pudo ejecutar ({type(error).__name__})"
        )
    first_line = completed.stdout.splitlines()[0] if completed.stdout else ""
    # ponytail: the first line already reads "ffmpeg version X"; drop the rest.
    version = first_line.split(" Copyright")[0].strip() or "versión desconocida"
    return DoctorCheck(name, "ok", version)


def _check_port(
    host: str, port: int, port_in_use: Callable[[str, int], bool]
) -> DoctorCheck:
    try:
        busy = port_in_use(host, port)
    except OSError as error:
        return DoctorCheck(
            "puerto",
            "warn",
            f"no se pudo comprobar {host}:{port} ({type(error).__name__})",
        )
    if busy:
        return DoctorCheck(
            "puerto",
            "warn",
            f"{host}:{port} ocupado; posiblemente VOZ ya está corriendo",
        )
    return DoctorCheck("puerto", "ok", f"{host}:{port} libre")


def _check_paths(paths: VozPaths, *, redact: bool) -> DoctorCheck:
    labelled = (
        ("config", paths.config),
        ("data", paths.data),
        ("cache", paths.cache),
        ("state", paths.state),
    )
    writable: list[str] = []
    blocked: list[str] = []
    for label, path in labelled:
        shown = label if redact else f"{label}={path}"
        try:
            path.mkdir(parents=True, exist_ok=True)
            ok = os.access(path, os.W_OK)
        except OSError:
            ok = False
        (writable if ok else blocked).append(shown)
    if blocked:
        return DoctorCheck(
            "rutas", "fail", "sin permiso de escritura: " + ", ".join(blocked)
        )
    suffix = " (rutas locales del usuario)" if redact else ""
    return DoctorCheck("rutas", "ok", "escribibles: " + ", ".join(writable) + suffix)


def _check_disk(data: Path, free_bytes: Callable[[Path], int]) -> DoctorCheck:
    try:
        free = free_bytes(data)
    except OSError as error:
        return DoctorCheck(
            "disco",
            "warn",
            f"no se pudo medir el espacio libre ({type(error).__name__})",
        )
    free_gib = free / 1024**3
    if free < MIN_FREE_BYTES:
        return DoctorCheck(
            "disco",
            "warn",
            f"{free_gib:.1f} GiB libres en data; se recomiendan >= 2 GiB",
        )
    return DoctorCheck("disco", "ok", f"{free_gib:.1f} GiB libres en data")


def _check_runtime(runtime_probe: TranscriptionRuntimeProbe) -> DoctorCheck:
    try:
        availability = runtime_probe.probe("faster-whisper")
    except Exception as error:  # diagnostics must never crash
        return DoctorCheck(
            "runtime ASR", "warn", f"sonda falló ({type(error).__name__})"
        )
    if availability.available:
        return DoctorCheck("runtime ASR", "ok", "faster-whisper disponible")
    return DoctorCheck(
        "runtime ASR",
        "warn",
        "extra asr-local no instalado (uv sync --extra asr-local)",
    )


def _check_gpu(hardware_probe: HardwareProbe) -> DoctorCheck:
    try:
        hardware = hardware_probe.probe()
    except Exception as error:  # never fail on hardware probing
        return DoctorCheck(
            "GPU/CUDA", "warn", f"detección no disponible ({type(error).__name__})"
        )
    cpu = ", ".join(sorted(hardware.cpu_compute_types)) or "ninguna"
    if hardware.cuda_compute_types:
        cuda = ", ".join(sorted(hardware.cuda_compute_types))
        return DoctorCheck("GPU/CUDA", "ok", f"CUDA: {cuda}; CPU: {cpu}")
    return DoctorCheck("GPU/CUDA", "warn", f"solo CPU ({cpu})")


def run_doctor(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    paths: VozPaths | None = None,
    redact: bool = False,
    which: Which = shutil.which,
    run: Run = _run_version,
    port_in_use: Callable[[str, int], bool] = _port_in_use,
    free_bytes: Callable[[Path], int] = _free_bytes,
    runtime_probe: TranscriptionRuntimeProbe | None = None,
    hardware_probe: HardwareProbe | None = None,
) -> DoctorReport:
    """Run every local prerequisite check; dependencies are injectable for tests."""
    resolved = resolve_voz_paths() if paths is None else paths
    return DoctorReport(
        (
            _check_tool("ffmpeg", which, run),
            _check_tool("ffprobe", which, run),
            _check_port(host, port, port_in_use),
            _check_paths(resolved, redact=redact),
            _check_disk(resolved.data, free_bytes),
            _check_runtime(runtime_probe or FasterWhisperRuntimeProbe()),
            _check_gpu(hardware_probe or CTranslate2HardwareProbe()),
        )
    )


def render(report: DoctorReport) -> str:
    """Human-readable Spanish table."""
    width = max(len(check.name) for check in report.checks)
    lines = ["Diagnóstico VOZ"]
    lines.extend(
        f"  [{_STATUS_LABEL[check.status]:<5}] {check.name:<{width}}  {check.detail}"
        for check in report.checks
    )
    counts = {status: 0 for status in _STATUS_LABEL}
    for check in report.checks:
        counts[check.status] += 1
    lines.append(
        f"Resumen: {counts['ok']} ok, {counts['warn']} avisos, {counts['fail']} fallos."
    )
    return "\n".join(lines)


def exit_code(report: DoctorReport) -> int:
    return 1 if report.has_failures else 0


__all__ = [
    "DoctorCheck",
    "DoctorReport",
    "HardwareProbe",
    "Run",
    "Which",
    "exit_code",
    "render",
    "run_doctor",
]
