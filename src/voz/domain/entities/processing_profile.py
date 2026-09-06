"""Provider-neutral processing profiles for local model execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import cast


class ProcessingProfileName(StrEnum):
    FAST = "fast"
    QUALITY = "quality"


class DevicePreference(StrEnum):
    GPU_PREFERRED = "gpu_preferred"
    CPU_ONLY = "cpu_only"


class ComputePrecision(StrEnum):
    FLOAT16 = "float16"
    INT8_FLOAT16 = "int8_float16"
    INT8 = "int8"


@dataclass(frozen=True, slots=True)
class ProcessingProfile:
    """Canonical performance intent without SDK-specific objects."""

    name: ProcessingProfileName
    device_preference: DevicePreference
    gpu_precisions: tuple[ComputePrecision, ...]
    cpu_precision: ComputePrecision

    def __post_init__(self) -> None:
        raw_name = cast(object, self.name)
        raw_preference = cast(object, self.device_preference)
        raw_gpu_precisions = cast(object, self.gpu_precisions)
        raw_cpu_precision = cast(object, self.cpu_precision)
        if not isinstance(raw_name, ProcessingProfileName):
            raise TypeError("name must be a ProcessingProfileName")
        if not isinstance(raw_preference, DevicePreference):
            raise TypeError("device_preference must be a DevicePreference")
        if not isinstance(raw_gpu_precisions, tuple):
            raise TypeError("gpu_precisions must be a tuple")
        gpu_precisions = cast(tuple[object, ...], raw_gpu_precisions)
        if any(not isinstance(item, ComputePrecision) for item in gpu_precisions):
            raise TypeError("gpu_precisions must contain ComputePrecision values")
        if not isinstance(raw_cpu_precision, ComputePrecision):
            raise TypeError("cpu_precision must be a ComputePrecision")
        if (
            self.device_preference is DevicePreference.GPU_PREFERRED
            and not self.gpu_precisions
        ):
            raise ValueError("a GPU-preferred profile needs a GPU precision")


__all__ = [
    "ComputePrecision",
    "DevicePreference",
    "ProcessingProfile",
    "ProcessingProfileName",
]
