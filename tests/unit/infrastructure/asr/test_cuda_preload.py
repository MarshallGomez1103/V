"""The optional pip CUDA wheels are preloaded without failing when absent."""

import ctypes
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from voz.infrastructure.asr import faster_whisper


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
