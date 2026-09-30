"""Diarization readiness probe: installed models plus the optional runtime wheel."""

from __future__ import annotations

from collections.abc import Callable
from importlib.util import find_spec

from voz.infrastructure.diarization.models import DiarizationModelStore


def _has_runtime() -> bool:
    return find_spec("sherpa_onnx") is not None


class SherpaDiarizationAvailability:
    """Implements ``DiarizationAvailability`` without importing or loading anything."""

    def __init__(
        self,
        store: DiarizationModelStore,
        *,
        has_runtime: Callable[[], bool] = _has_runtime,
    ) -> None:
        self._store = store
        self._has_runtime = has_runtime

    def is_available(self) -> bool:
        return self._store.is_installed() and self._has_runtime()


__all__ = ["SherpaDiarizationAvailability"]
