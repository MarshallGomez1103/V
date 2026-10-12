"""Unit tests for deterministic speech-synthesis provider registration."""

from __future__ import annotations

import pytest

from voz.application.synthesis_provider_registry import (
    DuplicateSynthesisProviderError,
    InvalidSynthesisProviderError,
    SynthesisProviderNotFoundError,
    SynthesisProviderRegistry,
)
from voz.infrastructure.tts.fake import FakeSpeechSynthesisProvider


class _Named(FakeSpeechSynthesisProvider):
    def __init__(self, provider_id: str) -> None:
        super().__init__()
        self._info = type(self._info)(provider_id=provider_id, display_name="X")


class _Incomplete:
    def describe(self) -> object:
        raise AssertionError


class _NonCallable(FakeSpeechSynthesisProvider):
    synthesize = 42  # type: ignore[assignment]


class _BadDescribe(FakeSpeechSynthesisProvider):
    def describe(self) -> object:  # type: ignore[override]
        return {"provider_id": "x"}


def test_registry_sorts_and_looks_up_by_described_id() -> None:
    registry = SynthesisProviderRegistry((_Named("zeta"), _Named("alpha")))

    assert registry.provider_ids() == ("alpha", "zeta")
    assert [p.describe().provider_id for p in registry.list_all()] == ["alpha", "zeta"]
    assert len(registry) == 2
    assert registry.get("zeta").describe().provider_id == "zeta"


def test_registry_rejects_duplicates() -> None:
    registry = SynthesisProviderRegistry((_Named("dup"),))

    with pytest.raises(DuplicateSynthesisProviderError) as raised:
        registry.register(_Named("dup"))

    assert raised.value.provider_id == "dup"


@pytest.mark.parametrize("candidate", [_Incomplete(), _NonCallable(), _BadDescribe()])
def test_registry_rejects_incomplete_contracts(candidate: object) -> None:
    with pytest.raises(InvalidSynthesisProviderError):
        SynthesisProviderRegistry().register(candidate)


def test_unknown_id_is_a_typed_lookup_error() -> None:
    with pytest.raises(SynthesisProviderNotFoundError):
        SynthesisProviderRegistry().get("missing")


def test_close_all_closes_every_engine() -> None:
    engines = (_Named("a"), _Named("b"))

    SynthesisProviderRegistry(engines).close_all()

    assert all(engine.closed for engine in engines)
