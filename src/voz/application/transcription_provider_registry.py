"""Deterministic registry for provider-neutral transcription adapters."""

from __future__ import annotations

from collections.abc import Iterable

from voz.application.ports import TranscriptionProvider

_PROVIDER_ID_CHARACTERS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789._-")


class InvalidTranscriptionProviderError(TypeError):
    """A candidate does not satisfy the provider contract or identity rules."""


class DuplicateTranscriptionProviderError(ValueError):
    """A provider is already registered under the requested identity."""

    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        super().__init__(
            f"A transcription provider is already registered as {provider_id!r}."
        )


class TranscriptionProviderNotFoundError(LookupError):
    """No transcription provider is registered under the requested identity."""

    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        super().__init__(f"No transcription provider is registered as {provider_id!r}.")


class TranscriptionProviderRegistry:
    """Register providers by stable ID and expose deterministic snapshots."""

    def __init__(
        self,
        providers: Iterable[TranscriptionProvider] = (),
    ) -> None:
        self._providers: dict[str, TranscriptionProvider] = {}
        for provider in providers:
            self.register(provider)

    def __len__(self) -> int:
        return len(self._providers)

    def register(self, provider: object) -> None:
        """Register one structurally compatible provider without replacement."""

        if not isinstance(provider, TranscriptionProvider):
            raise InvalidTranscriptionProviderError(
                "The candidate does not implement the transcription provider contract."
            )
        if not callable(provider.transcribe):
            raise InvalidTranscriptionProviderError(
                "The candidate transcription entrypoint must be callable."
            )

        provider_id = provider.provider_id
        if not _is_safe_provider_id(provider_id):
            raise InvalidTranscriptionProviderError(
                "The transcription provider_id must be a safe stable identifier."
            )
        if provider_id in self._providers:
            raise DuplicateTranscriptionProviderError(provider_id)

        self._providers[provider_id] = provider

    def get(self, provider_id: str) -> TranscriptionProvider:
        """Return a provider by exact ID or raise a typed lookup error."""

        try:
            return self._providers[provider_id]
        except KeyError:
            raise TranscriptionProviderNotFoundError(provider_id) from None

    def provider_ids(self) -> tuple[str, ...]:
        """Return provider IDs in deterministic lexical order."""

        return tuple(sorted(self._providers))

    def list_all(self) -> tuple[TranscriptionProvider, ...]:
        """Return an immutable provider snapshot in deterministic ID order."""

        return tuple(self._providers[key] for key in sorted(self._providers))


def _is_safe_provider_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 64
        and value[0] in "abcdefghijklmnopqrstuvwxyz0123456789"
        and all(character in _PROVIDER_ID_CHARACTERS for character in value)
    )


__all__ = [
    "DuplicateTranscriptionProviderError",
    "InvalidTranscriptionProviderError",
    "TranscriptionProviderNotFoundError",
    "TranscriptionProviderRegistry",
]
