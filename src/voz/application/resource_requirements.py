"""Approximate RAM/VRAM needed to load a model, and the guard built on it."""

from __future__ import annotations

from dataclasses import dataclass

from voz.application.asr_device_selection import (
    ComputeDevice,
    ExecutionDecision,
    HardwareCapabilities,
)
from voz.domain.entities.processing_profile import ComputePrecision

# ponytail: these are conservative estimates (MiB) derived from the published
# faster-whisper/CTranslate2 memory figures and rounded up, not measurements of
# VOZ itself; refine with real benchmarks. Keyed by catalog model id.
_VRAM_FLOAT16_MIB = {
    "tiny": 600,
    "base": 800,
    "small": 1500,
    "medium": 3000,
    "turbo": 2500,
    "large-v3": 5000,
}
_RAM_INT8_MIB = {
    "tiny": 500,
    "base": 600,
    "small": 1000,
    "medium": 2200,
    "turbo": 2200,
    "large-v3": 3500,
}
_INT8_VRAM_FACTOR = 0.7  # int8 / int8_float16 weights are about half of float16
_NON_INT8_RAM_FACTOR = 2.0  # float16/float32 on CPU keep wider weights


def required_memory_mib(
    model_id: str, device: ComputeDevice, precision: ComputePrecision
) -> int | None:
    """Estimated MiB for ``model_id``; ``None`` when the model is not in the table."""
    if device is ComputeDevice.CUDA:
        base = _VRAM_FLOAT16_MIB.get(model_id)
        if base is None:
            return None
        factor = 1.0 if precision is ComputePrecision.FLOAT16 else _INT8_VRAM_FACTOR
        return round(base * factor)
    base = _RAM_INT8_MIB.get(model_id)
    if base is None:
        return None
    factor = 1.0 if precision is ComputePrecision.INT8 else _NON_INT8_RAM_FACTOR
    return round(base * factor)


@dataclass(frozen=True, slots=True)
class MemoryShortfall:
    device: ComputeDevice
    required_mib: int
    available_mib: int


def find_shortfall(
    model_id: str, execution: ExecutionDecision, hardware: HardwareCapabilities
) -> MemoryShortfall | None:
    """Shortfall on the selected device, or ``None`` if it fits or is unmeasured."""
    required = required_memory_mib(model_id, execution.device, execution.precision)
    available = (
        hardware.vram_free_mib
        if execution.device is ComputeDevice.CUDA
        else hardware.ram_available_mib
    )
    if required is None or available is None or available >= required:
        return None
    return MemoryShortfall(execution.device, required, available)


__all__ = ["MemoryShortfall", "find_shortfall", "required_memory_mib"]
