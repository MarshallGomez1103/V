"""CTranslate2 capability probe kept behind the infrastructure boundary."""

from __future__ import annotations

import importlib
from collections.abc import Iterable
from contextlib import suppress
from typing import cast

from voz.application.asr_device_selection import HardwareCapabilities
from voz.application.ports.transcription import (
    TranscriptionError,
    TranscriptionFailureCode,
)
from voz.domain.entities.processing_profile import ComputePrecision


def _known_precisions(values: Iterable[object]) -> frozenset[ComputePrecision]:
    result: set[ComputePrecision] = set()
    for value in values:
        if isinstance(value, str):
            with suppress(ValueError):
                result.add(ComputePrecision(value))
    return frozenset(result)


class CTranslate2HardwareProbe:
    """Detect supported CPU/CUDA compute types without loading an ASR model."""

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
        return HardwareCapabilities(
            cuda_compute_types=_known_precisions(cuda_values),
            cpu_compute_types=_known_precisions(cpu_values),
        )


__all__ = ["CTranslate2HardwareProbe"]
