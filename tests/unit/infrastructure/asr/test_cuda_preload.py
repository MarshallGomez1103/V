"""The optional pip CUDA wheels are preloaded without failing when absent."""

import ctypes
import importlib
import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from voz.infrastructure.asr import faster_whisper

requires_posix = pytest.mark.skipif(os.name == "nt", reason="RTLD_GLOBAL is POSIX")


@requires_posix
def test_preload_retries_until_dependencies_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lib = tmp_path / "lib"
    lib.mkdir()
    for name in ("liba.so.1", "libb.so.1"):
        (lib / name).touch()
    loaded: list[str] = []

    def fake_cdll(path: str, mode: int = 0) -> None:
        name = Path(path).name
        # liba depends on libb: fails until libb is loaded.
        if name == "liba.so.1" and "libb.so.1" not in loaded:
            raise OSError("missing dependency")
        assert mode == ctypes.RTLD_GLOBAL
        loaded.append(name)

    def fake_import(name: str) -> object:
        if name == "nvidia.cublas":
            return SimpleNamespace(__path__=[str(tmp_path)])
        raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    monkeypatch.setattr(ctypes, "CDLL", fake_cdll)
    faster_whisper._preload_cuda_libraries()  # pyright: ignore[reportPrivateUsage]
    assert loaded == ["libb.so.1", "liba.so.1"]


@requires_posix
def test_preload_stops_when_nothing_can_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "libx.so.1").touch()

    def fail(path: str, mode: int = 0) -> None:
        raise OSError("nope")

    def fake_import(name: str) -> object:
        return SimpleNamespace(__path__=[str(tmp_path)])

    monkeypatch.setattr(importlib, "import_module", fake_import)
    monkeypatch.setattr(ctypes, "CDLL", fail)
    faster_whisper._preload_cuda_libraries()  # pyright: ignore[reportPrivateUsage]


def _fake_nvidia(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    def fake_import(name: str) -> object:
        if name == "nvidia.cublas":
            return SimpleNamespace(__path__=[str(tmp_path)])
        raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    return bin_dir


def test_windows_registers_dll_folders_and_loads_entry_dlls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = _fake_nvidia(tmp_path, monkeypatch)
    added: list[str] = []
    loaded: list[str] = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os, "add_dll_directory", added.append, raising=False)
    monkeypatch.setattr(ctypes, "WinDLL", loaded.append, raising=False)
    monkeypatch.setenv("PATH", "base")
    monkeypatch.setattr(faster_whisper, "_dll_directory_handles", [])

    ready = faster_whisper._preload_cuda_libraries()  # pyright: ignore[reportPrivateUsage]

    assert ready is True
    assert added == [str(bin_dir)]
    assert os.environ["PATH"].split(os.pathsep) == [str(bin_dir), "base"]
    assert loaded == ["cublas64_12.dll", "cudnn64_9.dll"]


def test_windows_reports_unloadable_cuda_dlls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_nvidia(tmp_path, monkeypatch)

    def fail(name: str) -> None:
        raise OSError(name)

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os, "add_dll_directory", str, raising=False)
    monkeypatch.setattr(ctypes, "WinDLL", fail, raising=False)
    monkeypatch.setattr(faster_whisper, "_dll_directory_handles", [])

    assert faster_whisper._preload_cuda_libraries() is False  # pyright: ignore[reportPrivateUsage]


class _Whisper:
    calls: list[tuple[str, str]]

    def __init__(self, fail_cuda: bool) -> None:
        self.calls = []
        self.fail_cuda = fail_cuda

    def WhisperModel(
        self, path: str, *, device: str, compute_type: str, local_files_only: bool
    ) -> str:
        self.calls.append((device, compute_type))
        if device == "cuda" and self.fail_cuda:
            raise RuntimeError("Library cublas64_12.dll is not found")
        return "engine"


def _install_fake_whisper(
    monkeypatch: pytest.MonkeyPatch, fake: _Whisper, *, preload_ok: bool
) -> None:
    real_import = importlib.import_module

    def fake_import(name: str, *args: Any) -> object:
        if name == "faster_whisper":
            return SimpleNamespace(WhisperModel=fake.WhisperModel)
        return real_import(name, *args)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    monkeypatch.setattr(faster_whisper, "_preload_cuda_libraries", lambda: preload_ok)


def _enable_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    # Alembic's fileConfig in other tests may have disabled existing loggers.
    logger = faster_whisper._logger  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(logger, "disabled", False)


def test_broken_cuda_runtime_falls_back_to_cpu_int8_with_a_message(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    fake = _Whisper(fail_cuda=False)
    _install_fake_whisper(monkeypatch, fake, preload_ok=False)
    _enable_logger(monkeypatch)

    with caplog.at_level(logging.WARNING):
        engine = faster_whisper._default_engine_factory(  # pyright: ignore[reportPrivateUsage]
            "m", device="cuda", compute_type="float16", local_files_only=True
        )

    assert engine == "engine"
    assert fake.calls == [("cpu", "int8")]
    assert "CUDA no está disponible" in caplog.text


def test_cuda_model_load_failure_retries_on_cpu_instead_of_failing_the_job(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    fake = _Whisper(fail_cuda=True)
    _install_fake_whisper(monkeypatch, fake, preload_ok=True)
    _enable_logger(monkeypatch)

    with caplog.at_level(logging.WARNING):
        engine = faster_whisper._default_engine_factory(  # pyright: ignore[reportPrivateUsage]
            "m", device="cuda", compute_type="float16", local_files_only=True
        )

    assert engine == "engine"
    assert fake.calls == [("cuda", "float16"), ("cpu", "int8")]
    assert "usa la CPU" in caplog.text


def test_cpu_load_errors_are_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    class Broken(_Whisper):
        def WhisperModel(
            self, path: str, *, device: str, compute_type: str, local_files_only: bool
        ) -> str:
            raise RuntimeError("bad model")

    _install_fake_whisper(monkeypatch, Broken(fail_cuda=False), preload_ok=True)

    with pytest.raises(RuntimeError):
        faster_whisper._default_engine_factory(  # pyright: ignore[reportPrivateUsage]
            "m", device="cpu", compute_type="int8", local_files_only=True
        )


def _without_nvidia_wheels(monkeypatch: pytest.MonkeyPatch, fake: _Whisper) -> None:
    """aarch64 installs skip nvidia-*-cu12: every nvidia import fails."""
    real_import = importlib.import_module

    def fake_import(name: str, *args: Any) -> object:
        if name == "faster_whisper":
            return SimpleNamespace(WhisperModel=fake.WhisperModel)
        if name.startswith("nvidia"):
            raise ImportError(name)
        return real_import(name, *args)

    monkeypatch.setattr(importlib, "import_module", fake_import)


def test_preload_without_nvidia_wheels_does_not_raise_on_linux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _without_nvidia_wheels(monkeypatch, _Whisper(fail_cuda=True))
    monkeypatch.setattr(sys, "platform", "linux")

    assert faster_whisper._nvidia_package_roots() == []  # pyright: ignore[reportPrivateUsage]
    assert faster_whisper._preload_cuda_libraries() is True  # pyright: ignore[reportPrivateUsage]


def test_preload_without_nvidia_wheels_reports_false_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _without_nvidia_wheels(monkeypatch, _Whisper(fail_cuda=True))

    def fail(name: str) -> None:
        raise OSError(name)

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", fail, raising=False)
    monkeypatch.setattr(faster_whisper, "_dll_directory_handles", [])

    assert faster_whisper._preload_cuda_libraries() is False  # pyright: ignore[reportPrivateUsage]


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_cuda_request_without_nvidia_wheels_ends_on_cpu_int8(
    platform: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _Whisper(fail_cuda=True)  # no CUDA runtime on the host either
    _without_nvidia_wheels(monkeypatch, fake)

    def no_dll(name: str) -> None:
        raise OSError(name)

    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(ctypes, "WinDLL", no_dll, raising=False)
    monkeypatch.setattr(faster_whisper, "_dll_directory_handles", [])

    engine = faster_whisper._default_engine_factory(  # pyright: ignore[reportPrivateUsage]
        "m", device="cuda", compute_type="float16", local_files_only=True
    )

    assert engine == "engine"
    assert fake.calls[-1] == ("cpu", "int8")
