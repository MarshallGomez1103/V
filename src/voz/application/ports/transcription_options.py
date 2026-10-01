"""Read-only model registration and runtime observations, without SDK types."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from voz.application.asr_device_selection import HardwareCapabilities
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor


class InstallationStatus(StrEnum):
    NOT_REGISTERED = "not_registered"
    REGISTERED = "registered"


@dataclass(frozen=True, slots=True)
class ModelRegistration:
    descriptor: ModelDescriptor
    installation_status: InstallationStatus
    files_available: bool = False
    cloud: bool = False  # audio leaves the machine; never installable or recommended
    provider_label: str | None = None  # visible provider name, cloud options only


@dataclass(frozen=True, slots=True)
class RuntimeAvailability:
    available: bool
    hardware: HardwareCapabilities | None = None
    capabilities: frozenset[ModelCapability] = frozenset()
    device_name: str | None = None


class TranscriptionOptionsUnavailable(Exception):
    """The local options cannot currently be inspected safely."""


class TranscriptionModelCatalog(Protocol):
    def list_models(self) -> tuple[ModelRegistration, ...]: ...


class TranscriptionRuntimeProbe(Protocol):
    def probe(self, provider_id: str) -> RuntimeAvailability: ...
