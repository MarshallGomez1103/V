"""Unit tests for deterministic transcription-provider registration."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import BinaryIO

import pytest

from voz.application.ports import (
    TranscriptionCancellationToken,
    TranscriptionOptions,
    TranscriptionProvider,
    TranscriptionResult,
)
from voz.application.transcription_provider_registry import (
    DuplicateTranscriptionProviderError,
    InvalidTranscriptionProviderError,
    TranscriptionProviderNotFoundError,
    TranscriptionProviderRegistry,
)


class _Provider:
    def __init__(self, provider_id: str) -> None:
        self._provider_id = provider_id

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        raise NotImplementedError


class _IncompleteProvider:
    provider_id = "incomplete"


class _NonCallableProvider:
    provider_id = "broken-asr"
    transcribe = 42


def _accept_provider(provider: TranscriptionProvider) -> TranscriptionProvider:
    """Make Pyright verify structural conformance of the test provider."""

    return provider


def test_registry_looks_up_providers_by_their_declared_stable_id() -> None:
    local = _accept_provider(_Provider("local-asr"))
    registry = TranscriptionProviderRegistry((local,))

    assert registry.get("local-asr") is local
    assert registry.provider_ids() == ("local-asr",)
    assert len(registry) == 1


def test_registry_listing_is_sorted_and_independent_of_registration_order() -> None:
    zebra = _accept_provider(_Provider("zebra-asr"))
    alpha = _accept_provider(_Provider("alpha-asr"))
    middle = _accept_provider(_Provider("middle-asr"))
    registry = TranscriptionProviderRegistry((zebra, alpha))

    registry.register(middle)

    assert registry.provider_ids() == ("alpha-asr", "middle-asr", "zebra-asr")
    assert registry.list_all() == (alpha, middle, zebra)


def test_listing_returns_an_immutable_snapshot() -> None:
    first = _accept_provider(_Provider("first-asr"))
    second = _accept_provider(_Provider("second-asr"))
    registry = TranscriptionProviderRegistry((first,))

    snapshot = registry.list_all()
    registry.register(second)

    assert snapshot == (first,)
    assert registry.list_all() == (first, second)


def test_duplicate_registration_is_rejected_without_replacing_provider() -> None:
    original = _accept_provider(_Provider("local-asr"))
    duplicate = _accept_provider(_Provider("local-asr"))
    registry = TranscriptionProviderRegistry((original,))

    with pytest.raises(DuplicateTranscriptionProviderError) as raised:
        registry.register(duplicate)

    assert raised.value.provider_id == "local-asr"
    assert registry.get("local-asr") is original
    assert registry.list_all() == (original,)


def test_unknown_provider_raises_typed_error() -> None:
    registry = TranscriptionProviderRegistry()

    with pytest.raises(TranscriptionProviderNotFoundError) as raised:
        registry.get("missing-asr")

    assert raised.value.provider_id == "missing-asr"


@pytest.mark.parametrize(
    "provider_id",
    ["", " Local ", "local/provider", "UPPERCASE", "line\nbreak"],
)
def test_registry_rejects_unsafe_or_ambiguous_provider_ids(provider_id: str) -> None:
    registry = TranscriptionProviderRegistry()

    with pytest.raises(InvalidTranscriptionProviderError, match="provider_id"):
        registry.register(_Provider(provider_id))

    assert registry.list_all() == ()


def test_registry_rejects_objects_that_do_not_implement_the_provider_port() -> None:
    registry = TranscriptionProviderRegistry()

    with pytest.raises(InvalidTranscriptionProviderError, match="contract"):
        registry.register(_IncompleteProvider())  # type: ignore[arg-type]

    assert not isinstance(_IncompleteProvider(), TranscriptionProvider)
    assert registry.list_all() == ()


def test_registry_rejects_a_non_callable_transcription_entrypoint() -> None:
    registry = TranscriptionProviderRegistry()

    with pytest.raises(InvalidTranscriptionProviderError, match="callable"):
        registry.register(_NonCallableProvider())

    assert registry.list_all() == ()


def test_registry_has_no_domain_infrastructure_or_framework_imports() -> None:
    module_path = (
        Path(__file__).parents[3]
        / "src"
        / "voz"
        / "application"
        / "transcription_provider_registry.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=module_path)
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert imported_modules <= {
        "__future__",
        "collections.abc",
        "typing",
        "voz.application.ports",
    }
