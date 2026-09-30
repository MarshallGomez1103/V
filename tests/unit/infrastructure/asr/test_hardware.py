"""Tests for CTranslate2 capability detection without loading a model."""

from types import ModuleType

import pytest

from voz.domain.entities.processing_profile import ComputePrecision
from voz.infrastructure.asr import hardware
from voz.infrastructure.asr.hardware import CTranslate2HardwareProbe
from voz.infrastructure.asr.system_resources import GpuMemory, SystemMemory


def test_probe_reports_known_cpu_and_cuda_compute_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = ModuleType("ctranslate2")

    def get_supported_compute_types(device: str) -> set[str]:
        assert device in {"cpu", "cuda"}
        return {"int8", "float16", "unknown"}

    runtime.__dict__["get_supported_compute_types"] = get_supported_compute_types

    def import_module(name: str) -> ModuleType:
        assert name == "ctranslate2"
        return runtime

    monkeypatch.setattr(hardware.importlib, "import_module", import_module)

    capabilities = CTranslate2HardwareProbe().probe()

    assert capabilities.cpu_compute_types == frozenset(
        {ComputePrecision.INT8, ComputePrecision.FLOAT16}
    )
    assert capabilities.cuda_compute_types == frozenset(
        {ComputePrecision.INT8, ComputePrecision.FLOAT16}
    )


def test_probe_treats_cuda_runtime_failure_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = ModuleType("ctranslate2")

    def get_supported_compute_types(device: str) -> set[str]:
        if device == "cuda":
            raise RuntimeError("no driver")
        return {"int8"}

    runtime.__dict__["get_supported_compute_types"] = get_supported_compute_types

    def import_module(name: str) -> ModuleType:
        assert name == "ctranslate2"
        return runtime

    monkeypatch.setattr(hardware.importlib, "import_module", import_module)

    capabilities = CTranslate2HardwareProbe().probe()

    assert capabilities.cpu_compute_types == frozenset({ComputePrecision.INT8})
    assert capabilities.cuda_compute_types == frozenset()


def _fake_ctranslate2(monkeypatch: pytest.MonkeyPatch, cuda: bool) -> None:
    runtime = ModuleType("ctranslate2")

    def get_supported_compute_types(device: str) -> set[str]:
        if device == "cuda" and not cuda:
            raise RuntimeError("no driver")
        return {"int8", "float16"}

    runtime.__dict__["get_supported_compute_types"] = get_supported_compute_types

    def import_module(name: str) -> ModuleType:
        return runtime

    monkeypatch.setattr(hardware.importlib, "import_module", import_module)


def test_probe_attaches_gpu_and_ram_measurements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_ctranslate2(monkeypatch, cuda=True)

    capabilities = CTranslate2HardwareProbe(
        gpu_reader=lambda: GpuMemory("RTX 4060 Laptop GPU", 8188, 7000),
        memory_reader=lambda: SystemMemory(64000, 30000),
    ).probe()

    assert capabilities.gpu_name == "RTX 4060 Laptop GPU"
    assert capabilities.vram_total_mib == 8188
    assert capabilities.vram_free_mib == 7000
    assert capabilities.ram_total_mib == 64000
    assert capabilities.ram_available_mib == 30000


def test_probe_leaves_measurements_none_when_readers_find_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_ctranslate2(monkeypatch, cuda=True)

    capabilities = CTranslate2HardwareProbe(
        gpu_reader=lambda: None, memory_reader=lambda: None
    ).probe()

    assert capabilities.gpu_name is None
    assert capabilities.vram_total_mib is None
    assert capabilities.ram_total_mib is None
    assert ComputePrecision.FLOAT16 in capabilities.cuda_compute_types


def test_probe_does_not_query_gpu_when_cuda_is_unusable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_ctranslate2(monkeypatch, cuda=False)

    def forbidden() -> GpuMemory:
        raise AssertionError("nvidia-smi must not run without CUDA")

    capabilities = CTranslate2HardwareProbe(
        gpu_reader=forbidden, memory_reader=lambda: SystemMemory(8000, 4000)
    ).probe()

    assert capabilities.vram_total_mib is None
    assert capabilities.ram_available_mib == 4000
