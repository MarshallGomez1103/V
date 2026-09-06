"""Tests for CTranslate2 capability detection without loading a model."""

from types import ModuleType

import pytest

from voz.domain.entities.processing_profile import ComputePrecision
from voz.infrastructure.asr import hardware
from voz.infrastructure.asr.hardware import CTranslate2HardwareProbe


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
