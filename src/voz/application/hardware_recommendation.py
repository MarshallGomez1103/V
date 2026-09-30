"""Pure hardware-aware model recommendation (S8.11).

The policy is declarative. It comes from the published CTranslate2 /
faster-whisper memory requirements and from timings measured on the target
machine (RTX 4060 Laptop, 8 GiB: turbo float16 and large-v3 float16 both load
in seconds and transcribe correctly), not from exhaustive VOZ benchmarks.

- CUDA, VRAM >= 6 GiB: ``turbo`` recommended (``gpu_fast_default``);
  ``large-v3`` not recommended but marked as fitting (``gpu_quality_fits``).
- CUDA, 5 GiB <= VRAM < 6 GiB: ``medium`` (``gpu_limited_medium``).
- CUDA, VRAM < 5 GiB: ``small`` (``gpu_limited_small``).
- CPU only, RAM >= 8 GiB: ``small`` (``cpu_default``).
- CPU only, RAM < 8 GiB: ``base`` (``cpu_low_ram``).

Without a measurement (``is_measured`` is false) the caller keeps the legacy
``default_compatible_profile`` behavior.
"""

from __future__ import annotations

from dataclasses import dataclass

from voz.application.asr_device_selection import HardwareCapabilities

_GIB = 1024
GPU_FULL_VRAM_MIB = 6 * _GIB
GPU_MEDIUM_VRAM_MIB = 5 * _GIB
CPU_LOW_RAM_MIB = 8 * _GIB


@dataclass(frozen=True, slots=True)
class Recommendation:
    recommended: bool
    reason: str


def is_measured(hardware: HardwareCapabilities) -> bool:
    """True when the measurement needed for the active device is present."""
    if hardware.cuda_compute_types:
        return hardware.vram_total_mib is not None
    return hardware.ram_total_mib is not None


def recommend(model_id: str, hardware: HardwareCapabilities) -> Recommendation | None:
    """Recommendation for one catalog model; ``None`` means "no opinion"."""
    if not is_measured(hardware):
        return None
    if hardware.cuda_compute_types:
        vram = hardware.vram_total_mib or 0
        if vram >= GPU_FULL_VRAM_MIB:
            if model_id == "turbo":
                return Recommendation(True, "gpu_fast_default")
            if model_id == "large-v3":
                return Recommendation(False, "gpu_quality_fits")
        elif vram >= GPU_MEDIUM_VRAM_MIB:
            if model_id == "medium":
                return Recommendation(True, "gpu_limited_medium")
        elif model_id == "small":
            return Recommendation(True, "gpu_limited_small")
        return None
    if (hardware.ram_total_mib or 0) < CPU_LOW_RAM_MIB:
        return Recommendation(True, "cpu_low_ram") if model_id == "base" else None
    return Recommendation(True, "cpu_default") if model_id == "small" else None


__all__ = ["Recommendation", "is_measured", "recommend"]
