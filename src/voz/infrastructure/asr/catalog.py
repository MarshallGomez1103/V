"""Faster Whisper descriptors and the canonical pinned model catalog."""

from dataclasses import dataclass, replace

from voz.application.ports.model_installation import ModelFile
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import (
    ComputePrecision,
    DevicePreference,
    ProcessingProfile,
    ProcessingProfileName,
)

_CAPABILITIES = frozenset(
    {
        ModelCapability.TRANSCRIPTION,
        ModelCapability.TRANSLATION,
        ModelCapability.LANGUAGE_DETECTION,
        ModelCapability.CPU,
        ModelCapability.GPU,
        ModelCapability.WORD_TIMESTAMPS,
    }
)


def faster_whisper_fast_descriptor(*, revision: str) -> ModelDescriptor:
    """Build the turbo profile pinned to ``revision`` (a 40-hex commit SHA).

    The revision is mandatory: an installable descriptor never lacks provenance.
    Models without an upstream commit (diarization) are not built here.
    """
    return ModelDescriptor(
        provider_id="faster-whisper",
        model_id="turbo",
        display_name="Faster Whisper Turbo (fast)",
        capabilities=_CAPABILITIES,
        source="mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        revision=revision,
        profile=ProcessingProfile(
            name=ProcessingProfileName.FAST,
            device_preference=DevicePreference.GPU_PREFERRED,
            gpu_precisions=(
                ComputePrecision.FLOAT16,
                ComputePrecision.INT8_FLOAT16,
            ),
            cpu_precision=ComputePrecision.INT8,
        ),
    )


def faster_whisper_quality_descriptor(*, revision: str) -> ModelDescriptor:
    """Build the large-v3 quality profile pinned to ``revision`` (mandatory)."""
    return ModelDescriptor(
        provider_id="faster-whisper",
        model_id="large-v3",
        display_name="Faster Whisper Large v3 (quality)",
        capabilities=_CAPABILITIES,
        source="Systran/faster-whisper-large-v3",
        revision=revision,
        profile=ProcessingProfile(
            name=ProcessingProfileName.QUALITY,
            device_preference=DevicePreference.GPU_PREFERRED,
            gpu_precisions=(ComputePrecision.FLOAT16,),
            cpu_precision=ComputePrecision.INT8,
        ),
    )


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """A pinned, downloadable model with the exact files VOZ expects."""

    descriptor: ModelDescriptor
    files: tuple[ModelFile, ...]
    license: str
    multilingual: bool

    def __post_init__(self) -> None:
        if self.descriptor.provenance is None:
            raise ValueError("catalog entries require a pinned source and revision")


def _files(
    model_bin: tuple[int, str], *others: tuple[str, int]
) -> tuple[ModelFile, ...]:
    # Only the LFS weights carry a SHA-256; the small text files are None.
    return (
        ModelFile("model.bin", model_bin[0], model_bin[1]),
        *(ModelFile(name, size, None) for name, size in others),
    )


def _entry(descriptor: ModelDescriptor, files: tuple[ModelFile, ...]) -> CatalogEntry:
    return CatalogEntry(descriptor, files, license="MIT", multilingual=True)


def _fast(model_id: str, label: str, source: str, revision: str) -> ModelDescriptor:
    return replace(
        faster_whisper_fast_descriptor(revision=revision),
        model_id=model_id,
        display_name=f"Faster Whisper {label} (fast)",
        source=source,
    )


_TURBO_REVISION = "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf"
_LARGE_V3_REVISION = "edaa852ec7e145841d8ffdb056a99866b5f0a478"
_MEDIUM_REVISION = "08e178d48790749d25932bbc082711ddcfdfbc4f"

_CATALOG = (
    _entry(
        _fast(
            "tiny",
            "Tiny",
            "Systran/faster-whisper-tiny",
            "d90ca5fe260221311c53c58e660288d3deb8d356",
        ),
        _files(
            (
                75538270,
                "dcb76c6586fc06cbdac6dd21f14cfd129cc4cdd9dce19bf4ffa62e59cbe6e6d1",
            ),
            ("config.json", 2249),
            ("tokenizer.json", 2203239),
            ("vocabulary.txt", 459861),
        ),
    ),
    _entry(
        _fast(
            "base",
            "Base",
            "Systran/faster-whisper-base",
            "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66",
        ),
        _files(
            (
                145217532,
                "d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9",
            ),
            ("config.json", 2309),
            ("tokenizer.json", 2203239),
            ("vocabulary.txt", 459861),
        ),
    ),
    _entry(
        _fast(
            "small",
            "Small",
            "Systran/faster-whisper-small",
            "536b0662742c02347bc0e980a01041f333bce120",
        ),
        _files(
            (
                483546902,
                "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671",
            ),
            ("config.json", 2370),
            ("tokenizer.json", 2203239),
            ("vocabulary.txt", 459861),
        ),
    ),
    _entry(
        replace(
            faster_whisper_quality_descriptor(revision=_MEDIUM_REVISION),
            model_id="medium",
            display_name="Faster Whisper Medium (quality)",
            source="Systran/faster-whisper-medium",
        ),
        _files(
            (
                1527906378,
                "9b45e1009dcc4ab601eff815b61d80e60ce3fd8c74c1a14f4a282258286b51ae",
            ),
            ("config.json", 2257),
            ("tokenizer.json", 2203239),
            ("vocabulary.txt", 459861),
        ),
    ),
    _entry(
        faster_whisper_quality_descriptor(revision=_LARGE_V3_REVISION),
        _files(
            (
                3087284237,
                "69f74147e3334731bc3a76048724833325d2ec74642fb52620eda87352e3d4f1",
            ),
            ("config.json", 2394),
            ("preprocessor_config.json", 340),
            ("tokenizer.json", 2480617),
            ("vocabulary.json", 1068114),
        ),
    ),
    _entry(
        faster_whisper_fast_descriptor(revision=_TURBO_REVISION),
        _files(
            (
                1617884929,
                "e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da",
            ),
            ("config.json", 2263),
            ("preprocessor_config.json", 340),
            ("tokenizer.json", 2710337),
            ("vocabulary.json", 1068114),
        ),
    ),
)


def faster_whisper_catalog() -> tuple[CatalogEntry, ...]:
    """Every model VOZ knows how to install, pinned to a verified revision."""
    return _CATALOG


class FasterWhisperModelCatalog:
    """``ModelCatalog`` port adapter over the static pinned catalog."""

    def entries(self) -> tuple[CatalogEntry, ...]:
        return _CATALOG


__all__ = [
    "CatalogEntry",
    "FasterWhisperModelCatalog",
    "faster_whisper_catalog",
    "faster_whisper_fast_descriptor",
    "faster_whisper_quality_descriptor",
]
