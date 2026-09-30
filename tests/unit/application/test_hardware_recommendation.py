"""S8.11/S14.05: pure recommendation policy and memory requirement table."""

import pytest

from voz.application.asr_device_selection import (
    ComputeDevice,
    ExecutionDecision,
    HardwareCapabilities,
)
from voz.application.hardware_recommendation import (
    Recommendation,
    is_measured,
    recommend,
)
from voz.application.resource_requirements import (
    find_shortfall,
    required_memory_mib,
)
from voz.domain.entities.processing_profile import ComputePrecision

CUDA = frozenset({ComputePrecision.FLOAT16})
CPU = frozenset({ComputePrecision.INT8})


def gpu(vram: int | None) -> HardwareCapabilities:
    return HardwareCapabilities(CUDA, CPU, "GPU", vram_total_mib=vram)


def cpu(ram: int | None) -> HardwareCapabilities:
    return HardwareCapabilities(frozenset(), CPU, ram_total_mib=ram)


@pytest.mark.parametrize(
    ("hardware", "expected"),
    [
        (
            gpu(8188),
            {
                "turbo": (True, "gpu_fast_default"),
                "large-v3": (False, "gpu_quality_fits"),
            },
        ),
        (
            gpu(6144),
            {
                "turbo": (True, "gpu_fast_default"),
                "large-v3": (False, "gpu_quality_fits"),
            },
        ),
        (
            gpu(5500),
            {"medium": (True, "gpu_limited_medium"), "turbo": None, "large-v3": None},
        ),
        (
            gpu(4096),
            {"small": (True, "gpu_limited_small"), "medium": None, "turbo": None},
        ),
        (cpu(16000), {"small": (True, "cpu_default"), "base": None, "turbo": None}),
        (cpu(4000), {"base": (True, "cpu_low_ram"), "small": None}),
    ],
)
def test_recommendation_follows_measured_hardware(
    hardware: HardwareCapabilities,
    expected: dict[str, tuple[bool, str] | None],
) -> None:
    for model_id, outcome in expected.items():
        got = recommend(model_id, hardware)
        assert got == (Recommendation(*outcome) if outcome else None), model_id


def test_unmeasured_hardware_has_no_opinion() -> None:
    assert not is_measured(gpu(None))
    assert not is_measured(cpu(None))
    assert recommend("turbo", gpu(None)) is None
    assert recommend("small", cpu(None)) is None


def test_requirements_scale_by_precision_and_ignore_unknown_models() -> None:
    fp16 = required_memory_mib("large-v3", ComputeDevice.CUDA, ComputePrecision.FLOAT16)
    int8 = required_memory_mib("large-v3", ComputeDevice.CUDA, ComputePrecision.INT8)
    assert fp16 is not None and int8 is not None and int8 < fp16
    assert (
        required_memory_mib("mystery", ComputeDevice.CUDA, ComputePrecision.FLOAT16)
        is None
    )
    ram_int8 = required_memory_mib("small", ComputeDevice.CPU, ComputePrecision.INT8)
    ram_fp32 = required_memory_mib(
        "small", ComputeDevice.CPU, ComputePrecision.INT8_FLOAT16
    )
    assert ram_int8 is not None and ram_fp32 is not None and ram_fp32 > ram_int8


def test_shortfall_compares_free_memory_of_the_selected_device() -> None:
    execution = ExecutionDecision(ComputeDevice.CUDA, ComputePrecision.FLOAT16)
    tight = HardwareCapabilities(CUDA, CPU, vram_free_mib=1000, ram_available_mib=99999)
    roomy = HardwareCapabilities(CUDA, CPU, vram_free_mib=8000)
    unmeasured = HardwareCapabilities(CUDA, CPU)

    shortfall = find_shortfall("large-v3", execution, tight)
    assert shortfall is not None
    assert (shortfall.required_mib, shortfall.available_mib) == (5000, 1000)
    assert find_shortfall("large-v3", execution, roomy) is None
    assert find_shortfall("large-v3", execution, unmeasured) is None
    assert find_shortfall("mystery", execution, tight) is None
