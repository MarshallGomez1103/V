"""whisper.cpp registrations and runtime probe for the transcription options."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from voz.application.asr_device_selection import HardwareCapabilities
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
    RuntimeAvailability,
)
from voz.domain.entities.processing_profile import ComputePrecision
from voz.infrastructure.asr.whisper_cpp import (
    WhisperCppAvailability,
    probe_whisper_cpp,
)
from voz.infrastructure.asr.whisper_cpp_catalog import (
    model_filename,
    whisper_cpp_catalog,
)
from voz.infrastructure.model_storage import FileSystemModelStore


@dataclass(frozen=True, slots=True)
class WhisperCppTranscriptionModelCatalog:
    """One option per pinned GGML file; installed means a single verified file."""

    store: FileSystemModelStore

    def list_models(self) -> tuple[ModelRegistration, ...]:
        registrations: list[ModelRegistration] = []
        for entry in whisper_cpp_catalog():
            descriptor = entry.descriptor
            if not self.store.is_installed(descriptor):
                registrations.append(
                    ModelRegistration(descriptor, InstallationStatus.NOT_REGISTERED)
                )
                continue
            path = self.store.resolve_path(descriptor) / model_filename(descriptor)
            available = (
                not path.is_symlink() and path.is_file() and path.stat().st_size > 0
            )
            registrations.append(
                ModelRegistration(descriptor, InstallationStatus.REGISTERED, available)
            )
        return tuple(registrations)


@dataclass(slots=True)
class WhisperCppRuntimeProbe:
    """Probe the executable once per process; CPU plan only (see catalog profile)."""

    probe_binary: Callable[[], WhisperCppAvailability] = probe_whisper_cpp
    _cached: WhisperCppAvailability | None = field(default=None, repr=False)

    def availability(self) -> WhisperCppAvailability:
        # ponytail: cached for the process lifetime; restart VOZ after installing
        # whisper-cli.
        if self._cached is None:
            self._cached = self.probe_binary()
        return self._cached

    def probe(self, provider_id: str) -> RuntimeAvailability:
        del provider_id
        capabilities = whisper_cpp_catalog()[0].descriptor.capabilities
        if not self.availability().available:
            return RuntimeAvailability(False, capabilities=capabilities)
        return RuntimeAvailability(
            True,
            hardware=HardwareCapabilities(
                cuda_compute_types=frozenset(),
                cpu_compute_types=frozenset(ComputePrecision),
            ),
            capabilities=capabilities,
        )


__all__ = ["WhisperCppRuntimeProbe", "WhisperCppTranscriptionModelCatalog"]
