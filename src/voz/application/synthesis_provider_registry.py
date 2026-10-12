"""Deterministic registry for provider-neutral speech synthesis engines."""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from voz.application.ports import SpeechSynthesisProvider, SynthesisProviderInfo

_ENTRYPOINTS = (
    "describe",
    "voices",
    "languages",
    "requirements",
    "synthesize",
    "close",
)


class InvalidSynthesisProviderError(TypeError):
    """A candidate does not satisfy the synthesis provider contract."""


class DuplicateSynthesisProviderError(ValueError):
    """A provider is already registered under the requested identity."""

    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        super().__init__(
            f"A synthesis provider is already registered as {provider_id!r}."
        )


class SynthesisProviderNotFoundError(LookupError):
    """No synthesis provider is registered under the requested identity."""

    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        super().__init__(f"No synthesis provider is registered as {provider_id!r}.")


class SynthesisProviderRegistry:
    """Register engines by the stable ID they describe; snapshots are sorted."""

    def __init__(self, providers: Iterable[SpeechSynthesisProvider] = ()) -> None:
        self._providers: dict[str, SpeechSynthesisProvider] = {}
        for provider in providers:
            self.register(provider)

    def __len__(self) -> int:
        return len(self._providers)

    def register(self, provider: object) -> None:
        """Register one structurally compatible provider without replacement."""

        if not isinstance(provider, SpeechSynthesisProvider):
            raise InvalidSynthesisProviderError(
                "The candidate does not implement the synthesis provider contract."
            )
        if not all(callable(getattr(provider, name)) for name in _ENTRYPOINTS):
            raise InvalidSynthesisProviderError(
                "The candidate synthesis entrypoints must be callable."
            )
        info = provider.describe()
        if not isinstance(cast(object, info), SynthesisProviderInfo):
            raise InvalidSynthesisProviderError(
                "describe() must return a SynthesisProviderInfo."
            )
        if info.provider_id in self._providers:
            raise DuplicateSynthesisProviderError(info.provider_id)
        self._providers[info.provider_id] = provider

    def get(self, provider_id: str) -> SpeechSynthesisProvider:
        """Return a provider by exact ID or raise a typed lookup error."""

        try:
            return self._providers[provider_id]
        except KeyError:
            raise SynthesisProviderNotFoundError(provider_id) from None

    def provider_ids(self) -> tuple[str, ...]:
        """Return provider IDs in deterministic lexical order."""

        return tuple(sorted(self._providers))

    def list_all(self) -> tuple[SpeechSynthesisProvider, ...]:
        """Return an immutable provider snapshot in deterministic ID order."""

        return tuple(self._providers[key] for key in sorted(self._providers))

    def close_all(self) -> None:
        """Close every engine; for application shutdown."""

        for provider in self.list_all():
            provider.close()


__all__ = [
    "DuplicateSynthesisProviderError",
    "InvalidSynthesisProviderError",
    "SynthesisProviderNotFoundError",
    "SynthesisProviderRegistry",
]
