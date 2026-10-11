"""Unit tests for ``voz doctor`` with every system dependency faked."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import zipfile
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest
from typer.testing import CliRunner

from voz.application.asr_device_selection import HardwareCapabilities
from voz.application.ports.transcription_options import (
    RuntimeAvailability,
    TranscriptionRuntimeProbe,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import ComputePrecision
from voz.infrastructure.model_storage import FileSystemModelStore
from voz.infrastructure.paths import VozPaths
from voz.interfaces.cli.doctor import (
    DoctorReport,
    HardwareProbe,
    ModelStoreView,
    Run,
    Which,
    exit_code,
    render,
    run_doctor,
)
from voz.interfaces.cli.main import app as cli_app

GIB = 1024**3
REVISION = "0123456789abcdef0123456789abcdef01234567"


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


def installed_store(root: Path, *, payload: bytes = b"weights") -> FileSystemModelStore:
    """A real store holding one model registered through a fake downloader."""
    snapshot = root / "remote-snapshot"
    snapshot.mkdir(exist_ok=True)
    (snapshot / "model.bin").write_bytes(payload)

    def download(**_kwargs: object) -> str:
        return str(snapshot)

    store = FileSystemModelStore(
        data_root=root / "data" / "voz",
        cache_root=root / "cache" / "voz",
        downloader_factory=lambda: download,
    )
    store.install(
        ModelDescriptor(
            provider_id="faster-whisper",
            model_id="turbo",
            display_name="Turbo",
            capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
            source="example/fixture",
            revision=REVISION,
        ),
        confirmed=True,
    )
    return store


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
    model_store: ModelStoreView | None = None,
    environ: Mapping[str, str] | None = None,
    python_executable: str = "/usr/bin/python",
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
        model_store=model_store or installed_store(tmp_path),
        environ={} if environ is None else environ,
        python_executable=python_executable,
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
    assert "Resumen: 11 ok, 0 avisos, 0 fallos." in rendered


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


def fake_v(directory: Path, name: str = "v") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    executable = directory / name
    # Never executed: the check must only compare paths.
    executable.write_text("#!/bin/sh\necho foreign-v-ran >&2\nexit 99\n")
    executable.chmod(0o755)
    return executable


def path_which(*directories: Path) -> Which:
    """Real ``shutil.which`` for v/voz over a simulated PATH; other tools stay faked."""
    search = os.pathsep.join(str(d) for d in directories)

    def which(name: str) -> str | None:
        if name in {"v", "voz"}:
            return shutil.which(name, path=search)
        return fake_which(name)

    return which


def v_check(report: DoctorReport) -> tuple[str, str]:
    check = next(c for c in report.checks if c.name == "comando v")
    return check.status, check.detail


def test_foreign_v_first_in_path_warns_without_running_it(tmp_path: Path) -> None:
    foreign = fake_v(tmp_path / "vlang")
    venv_bin = tmp_path / "venv" / "bin"
    fake_v(venv_bin)
    fake_v(venv_bin, "voz")

    report = healthy_report(
        tmp_path,
        which=path_which(foreign.parent, venv_bin),
        python_executable=str(venv_bin / "python"),
    )

    status, detail = v_check(report)
    assert status == "warn"
    assert "no es el de V" in detail
    assert str(tmp_path) not in detail
    assert exit_code(report) == 0


def test_missing_v_is_informational_not_a_failure(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    report = healthy_report(
        tmp_path,
        which=lambda name: None if name == "v" else f"/usr/bin/{name}",
        python_executable=str(tmp_path / "venv" / "bin" / "python"),
    )

    status, detail = v_check(report)
    assert status == "ok"
    assert "no hay `v` en PATH" in detail
    assert "uv run" in detail
    assert exit_code(report) == 0


def test_own_v_next_to_interpreter_is_ok(tmp_path: Path) -> None:
    venv_bin = tmp_path / "venv" / "bin"
    fake_v(venv_bin)

    report = healthy_report(
        tmp_path,
        which=path_which(venv_bin),
        python_executable=str(venv_bin / "python"),
    )

    assert v_check(report) == ("ok", "`v` en PATH es el de V")


def test_own_v_through_symlink_next_to_voz_is_ok(tmp_path: Path) -> None:
    # uv tool install: ~/.local/bin/v -> <tool venv>/bin/v
    tool_bin = tmp_path / "tools" / "voz-transcriber" / "bin"
    real = fake_v(tool_bin)
    fake_v(tool_bin, "voz")
    user_bin = tmp_path / "local-bin"
    user_bin.mkdir()
    (user_bin / "v").symlink_to(real)
    (user_bin / "voz").symlink_to(tool_bin / "voz")

    report = healthy_report(
        tmp_path,
        which=path_which(user_bin),
        python_executable=str(tool_bin / "python"),
    )

    assert v_check(report)[0] == "ok"


def test_busy_port_warns(tmp_path: Path) -> None:
    report = healthy_report(tmp_path, port_in_use=lambda _host, _port: True)

    port_check = next(check for check in report.checks if check.name == "puerto")
    assert port_check.status == "warn"
    assert "posiblemente VOZ ya está corriendo" in port_check.detail
    assert exit_code(report) == 0


def test_low_disk_space_warns(tmp_path: Path) -> None:
    report = healthy_report(tmp_path, free_bytes=lambda _path: GIB)

    assert statuses(report)["disco"] == "warn"


def test_low_cache_space_warns_even_when_data_is_roomy(tmp_path: Path) -> None:
    paths = tmp_paths(tmp_path)

    report = healthy_report(
        tmp_path,
        paths=paths,
        free_bytes=lambda path: GIB if path == paths.cache else 10 * GIB,
    )

    disk = next(c for c in report.checks if c.name == "disco")
    assert disk.status == "warn"
    assert "1.0 GiB libres en cache" in disk.detail
    assert "10.0 GiB libres en data" in disk.detail
    assert ">= 5 GiB" in disk.detail


def test_models_lists_id_revision_and_size_without_paths(tmp_path: Path) -> None:
    report = healthy_report(
        tmp_path, model_store=installed_store(tmp_path, payload=b"x" * 2048)
    )

    models = next(c for c in report.checks if c.name == "modelos")
    assert models.status == "ok"
    assert models.detail.startswith("faster-whisper/turbo rev 0123456789ab (")
    assert "GiB)" in models.detail
    assert str(tmp_path) not in models.detail


def test_no_registered_models_warns(tmp_path: Path) -> None:
    empty = FileSystemModelStore(
        data_root=tmp_path / "data" / "voz", cache_root=tmp_path / "cache" / "voz"
    )

    report = healthy_report(tmp_path, model_store=empty)

    models = next(c for c in report.checks if c.name == "modelos")
    assert models.status == "warn"
    assert "confirmación explícita" in models.detail
    assert exit_code(report) == 0


def test_model_store_failure_warns_with_type_only(tmp_path: Path) -> None:
    class Broken:
        def registered_descriptors(self) -> tuple[ModelDescriptor, ...]:
            raise OSError("/home/secret/models is unreadable")

        def resolve_path(self, descriptor: ModelDescriptor) -> Path:
            raise AssertionError

    report = healthy_report(tmp_path, model_store=Broken())

    models = next(c for c in report.checks if c.name == "modelos")
    assert models.status == "warn"
    assert "OSError" in models.detail
    assert "secret" not in models.detail


def test_optional_api_keys_report_presence_never_values(tmp_path: Path) -> None:
    secret = "sk-super-secret-value-123"
    report = healthy_report(
        tmp_path, environ={"OPENAI_API_KEY": secret, "ELEVENLABS_API_KEY": ""}
    )

    by_name = {c.name: c for c in report.checks}
    assert by_name["OPENAI_API_KEY"].detail.startswith("set (opcional")
    assert by_name["ELEVENLABS_API_KEY"].detail.startswith("unset (opcional")
    assert "no se usa salvo selección explícita" in by_name["OPENAI_API_KEY"].detail
    assert {c.status for c in report.checks} == {"ok"}
    assert secret not in render(report)
    assert "sk-" not in json.dumps([c.detail for c in report.checks])


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
        "comando v",
        "puerto",
        "rutas",
        "disco",
        "modelos",
        "runtime ASR",
        "GPU/CUDA",
        "OPENAI_API_KEY",
        "ELEVENLABS_API_KEY",
    ]
    assert all(check["status"] in {"ok", "warn", "fail"} for check in payload["checks"])
    assert (result.exit_code == 1) == any(
        check["status"] == "fail" for check in payload["checks"]
    )


def test_cli_doctor_bundle_writes_redacted_zip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for variable in ("CONFIG", "DATA", "CACHE", "STATE"):
        monkeypatch.setenv(f"XDG_{variable}_HOME", str(tmp_path / variable.lower()))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-must-not-leak")
    target = tmp_path / "bundle.zip"

    result = CliRunner().invoke(
        cli_app, ["doctor", "--bundle", str(target), "--port", "1"]
    )

    assert result.exit_code in {0, 1}
    with zipfile.ZipFile(target) as archive:
        assert sorted(archive.namelist()) == [
            "README.txt",
            "database.json",
            "doctor.json",
            "versions.json",
        ]
        text = "".join(archive.read(name).decode() for name in archive.namelist())
    assert str(tmp_path) not in text
    assert "sk-must-not-leak" not in text
    assert "OPENAI_API_KEY" in text
    again = CliRunner().invoke(cli_app, ["doctor", "--bundle", str(target)])
    assert again.exit_code == 2  # never overwrites an existing file
