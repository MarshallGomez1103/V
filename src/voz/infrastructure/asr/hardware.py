"""CTranslate2 capability probe kept behind the infrastructure boundary."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterable
from contextlib import suppress
from typing import cast

from voz.application.asr_device_selection import HardwareCapabilities
from voz.application.ports.transcription import (
    TranscriptionError,
    TranscriptionFailureCode,
)
from voz.domain.entities.processing_profile import ComputePrecision
from voz.infrastructure.asr.system_resources import (
    GpuMemory,
    SystemMemory,
    read_gpu_memory,
    read_system_memory,
)


def _known_precisions(values: Iterable[object]) -> frozenset[ComputePrecision]:
    result: set[ComputePrecision] = set()
    for value in values:
        if isinstance(value, str):
            with suppress(ValueError):
                result.add(ComputePrecision(value))
    return frozenset(result)


class CTranslate2HardwareProbe:
    """Detect supported CPU/CUDA compute types without loading an ASR model.

    GPU name/VRAM (``nvidia-smi``) and RAM (``/proc/meminfo``) are optional
    measurements; the readers are injectable and never raise.
    """

    def __init__(
        self,
        gpu_reader: Callable[[], GpuMemory | None] | None = None,
        memory_reader: Callable[[], SystemMemory | None] | None = None,
    ) -> None:
        self._gpu_reader = gpu_reader
        self._memory_reader = memory_reader

    def probe(self) -> HardwareCapabilities:
        try:
            module = importlib.import_module("ctranslate2")
            get_types = cast(object, vars(module)["get_supported_compute_types"])
            if not callable(get_types):
                raise TypeError
            cpu_values = cast(Iterable[object], get_types("cpu"))
        except (ImportError, KeyError, TypeError, RuntimeError) as error:
            raise TranscriptionError(
                TranscriptionFailureCode.PROVIDER_FAILED,
                "The CTranslate2 runtime is not available for hardware detection.",
            ) from error

        try:
            cuda_values = cast(Iterable[object], get_types("cuda"))
        except (ValueError, RuntimeError):
            cuda_values = ()
        cuda_types = _known_precisions(cuda_values)
        # Skip the subprocess when CUDA is not usable anyway.
        gpu = (self._gpu_reader or read_gpu_memory)() if cuda_types else None
        memory = (self._memory_reader or read_system_memory)()
        return HardwareCapabilities(
            cuda_compute_types=cuda_types,
            cpu_compute_types=_known_precisions(cpu_values),
            gpu_name=gpu.name if gpu else None,
            vram_total_mib=gpu.total_mib if gpu else None,
            vram_free_mib=gpu.free_mib if gpu else None,
            ram_total_mib=memory.total_mib if memory else None,
            ram_available_mib=memory.available_mib if memory else None,
        )


__all__ = ["CTranslate2HardwareProbe"]
