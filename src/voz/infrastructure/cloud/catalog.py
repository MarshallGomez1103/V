"""Cloud options for the transcription-options query: listed, never recommended.

A cloud model is ``available`` only when its API key is configured. Nothing is
enabled by that: a job must still select the option explicitly.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from voz.application.ports.provider_secrets import ProviderSecretsPort
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
    RuntimeAvailability,
    TranscriptionModelCatalog,
    TranscriptionRuntimeProbe,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor


@dataclass(frozen=True, slots=True)
class CloudTranscriptionCatalog:
    descriptors: tuple[ModelDescriptor, ...]
    # provider_id -> visible name; the backend is the source of truth for the UI.
    labels: Mapping[str, str] = field(default_factory=dict[str, str])

    def list_models(self) -> tuple[ModelRegistration, ...]:
        # Nothing to install: remote models are always "registered".
        return tuple(
            ModelRegistration(
                descriptor,
                InstallationStatus.REGISTERED,
                True,
                cloud=True,
                provider_label=self.labels.get(descriptor.provider_id),
            )
            for descriptor in self.descriptors
        )


class CloudRuntimeProbe:
    """Available iff the provider's key is configured; never contacts the network."""

    def __init__(
        self, secrets: ProviderSecretsPort, descriptors: Iterable[ModelDescriptor]
    ) -> None:
        self._secrets = secrets
        capabilities: dict[str, frozenset[ModelCapability]] = {}
        for descriptor in descriptors:
            known = capabilities.get(descriptor.provider_id, frozenset())
            capabilities[descriptor.provider_id] = known | descriptor.capabilities
        self._capabilities = capabilities

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._capabilities))

    def probe(self, provider_id: str) -> RuntimeAvailability:
        capabilities = self._capabilities.get(provider_id)
        if capabilities is None:
            return RuntimeAvailability(False)
        return RuntimeAvailability(
            self._secrets.configured(provider_id), capabilities=capabilities
        )


@dataclass(frozen=True, slots=True)
class CompositeCatalog:
    catalogs: tuple[TranscriptionModelCatalog, ...]

    def list_models(self) -> tuple[ModelRegistration, ...]:
        return tuple(
            registration
            for catalog in self.catalogs
            for registration in catalog.list_models()
        )


@dataclass(frozen=True, slots=True)
class RoutingRuntimeProbe:
    """Send known provider ids to their probe; everything else to ``default``."""

    default: TranscriptionRuntimeProbe
    routes: Mapping[str, TranscriptionRuntimeProbe]

    def probe(self, provider_id: str) -> RuntimeAvailability:
        return self.routes.get(provider_id, self.default).probe(provider_id)


__all__ = [
    "CloudRuntimeProbe",
    "CloudTranscriptionCatalog",
    "CompositeCatalog",
    "RoutingRuntimeProbe",
]
