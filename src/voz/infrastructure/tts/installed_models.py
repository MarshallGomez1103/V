"""The synthesis models installed right now, as a ``SynthesisModelCatalog``.

Read from the store on every call, so a model installed or deleted from the
Model Manager appears or disappears without a restart (V4-06).
"""

from __future__ import annotations

from collections.abc import Sequence

from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
)
from voz.domain.entities.model_descriptor import ModelCapability
from voz.infrastructure.tts.catalog import TTS_CATALOG, TtsModelEntry
from voz.infrastructure.tts.model_store import TtsModelStore


class InstalledTtsModels:
    """Registered, file-complete synthesis models of the pinned catalog."""

    def __init__(
        self, store: TtsModelStore, entries: Sequence[TtsModelEntry] = TTS_CATALOG
    ) -> None:
        self._store = store
        self._entries = tuple(
            entry
            for entry in entries
            if entry.descriptor.supports(ModelCapability.SYNTHESIS)
        )

    def list_models(self) -> tuple[ModelRegistration, ...]:
        return tuple(
            ModelRegistration(
                entry.descriptor, InstallationStatus.REGISTERED, files_available=True
            )
            for entry in self._entries
            if self._store.is_installed(entry.model_id)
        )


__all__ = ["InstalledTtsModels"]
