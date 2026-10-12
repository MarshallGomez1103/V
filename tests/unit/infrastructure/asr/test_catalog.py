"""Tests for Faster Whisper fast and quality descriptors."""

import inspect
from collections.abc import Callable
from dataclasses import replace

import pytest

from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import (
    ComputePrecision,
    ProcessingProfileName,
)
from voz.infrastructure.asr.catalog import (
    CatalogEntry,
    FasterWhisperModelCatalog,
    faster_whisper_catalog,
    faster_whisper_fast_descriptor,
    faster_whisper_quality_descriptor,
)


def test_fast_profile_uses_turbo_and_gpu_first_precisions() -> None:
    descriptor = faster_whisper_fast_descriptor(revision="a" * 40)

    assert descriptor.model_id == "turbo"
    assert descriptor.source == "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
    assert descriptor.revision == "a" * 40
    assert descriptor.profile is not None
    assert descriptor.profile.name is ProcessingProfileName.FAST
    assert descriptor.profile.gpu_precisions == (
        ComputePrecision.FLOAT16,
        ComputePrecision.INT8_FLOAT16,
    )
    assert descriptor.supports(ModelCapability.GPU)


def test_quality_profile_uses_large_v3_and_preserves_revision() -> None:
    descriptor = faster_whisper_quality_descriptor(revision="b" * 40)

    assert descriptor.model_id == "large-v3"
    assert descriptor.source == "Systran/faster-whisper-large-v3"
    assert descriptor.revision == "b" * 40
    assert descriptor.profile is not None
    assert descriptor.profile.name is ProcessingProfileName.QUALITY
    assert descriptor.profile.cpu_precision is ComputePrecision.INT8


def test_catalog_lists_six_pinned_models_matching_the_builders() -> None:
    entries = faster_whisper_catalog()

    assert [entry.descriptor.model_id for entry in entries] == [
        "tiny",
        "base",
        "small",
        "medium",
        "large-v3",
        "turbo",
    ]
    by_id = {entry.descriptor.model_id: entry for entry in entries}
    assert by_id["turbo"].descriptor == faster_whisper_fast_descriptor(
        revision="0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf"
    )
    assert by_id["large-v3"].descriptor == faster_whisper_quality_descriptor(
        revision="edaa852ec7e145841d8ffdb056a99866b5f0a478"
    )
    assert {
        entry.descriptor.model_id: getattr(entry.descriptor.profile, "name", None)
        for entry in entries
    } == {
        "tiny": ProcessingProfileName.FAST,
        "base": ProcessingProfileName.FAST,
        "small": ProcessingProfileName.FAST,
        "medium": ProcessingProfileName.QUALITY,
        "large-v3": ProcessingProfileName.QUALITY,
        "turbo": ProcessingProfileName.FAST,
    }
    assert all(entry.descriptor.provenance is not None for entry in entries)
    assert all(entry.license == "MIT" and entry.multilingual for entry in entries)


def test_catalog_files_pin_weights_only_and_expose_verified_sizes() -> None:
    by_id = {e.descriptor.model_id: e for e in faster_whisper_catalog()}

    assert (
        sum(f.size_bytes for f in by_id["tiny"].files)
        == 75538270 + 2249 + 2203239 + 459861
    )
    for entry in by_id.values():
        weights, *rest = entry.files
        assert weights.name == "model.bin"
        assert weights.sha256 is not None and len(weights.sha256) == 64
        assert all(file.sha256 is None for file in rest)
        names = {file.name for file in entry.files}
        assert {"config.json", "tokenizer.json"} <= names
        assert len(names & {"vocabulary.txt", "vocabulary.json"}) == 1
    assert "vocabulary.txt" in {f.name for f in by_id["small"].files}
    assert "vocabulary.json" in {f.name for f in by_id["turbo"].files}


def test_catalog_adapter_exposes_the_same_entries() -> None:
    assert FasterWhisperModelCatalog().entries() == faster_whisper_catalog()


@pytest.mark.parametrize(
    "builder", [faster_whisper_fast_descriptor, faster_whisper_quality_descriptor]
)
def test_descriptor_builders_require_a_pinned_revision(
    builder: Callable[..., ModelDescriptor],
) -> None:
    parameter = inspect.signature(builder).parameters["revision"]
    assert parameter.default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        builder()
    with pytest.raises((TypeError, ValueError)):
        builder(revision=None)
    with pytest.raises(ValueError):
        builder(revision="")
    with pytest.raises(ValueError):
        builder(revision="main")


def test_installable_catalog_entry_rejects_a_descriptor_without_provenance() -> None:
    pinned = faster_whisper_catalog()[0]
    unpinned = replace(pinned.descriptor, source=None, revision=None)

    with pytest.raises(ValueError, match="revision"):
        replace(pinned, descriptor=unpinned)
    with pytest.raises(ValueError, match="revision"):
        CatalogEntry(unpinned, pinned.files, license="MIT", multilingual=True)
