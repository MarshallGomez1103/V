"""Pinned GGML models for whisper.cpp (MIT, ``ggerganov/whisper.cpp``).

Each model is one ``ggml-<model_id>.bin`` file. ``FileSystemModelStore.download``
fits as-is: source and revision are fixed, the file list has a single item and
the verified file lands in the store directory that ``resolve_path`` returns.
"""

from __future__ import annotations

import re

from voz.application.ports.model_installation import ModelFile
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.processing_profile import (
    ComputePrecision,
    DevicePreference,
    ProcessingProfile,
    ProcessingProfileName,
)
from voz.infrastructure.asr.catalog import CatalogEntry

PROVIDER_ID = "whisper-cpp"
SOURCE = "ggerganov/whisper.cpp"
REVISION = "5359861c739e955e79d9a303bcbc70fb988958b1"

_CAPABILITIES = frozenset(
    {
        ModelCapability.TRANSCRIPTION,
        ModelCapability.LANGUAGE_DETECTION,
        ModelCapability.CPU,
        ModelCapability.GPU,
        ModelCapability.WORD_TIMESTAMPS,
    }
)
_SAFE_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", re.ASCII)


def model_filename(descriptor: ModelDescriptor) -> str:
    """Return the GGML file name inside an installed model directory."""
    if _SAFE_MODEL_ID.fullmatch(descriptor.model_id) is None:
        raise ValueError("model_id is not a safe whisper.cpp model name")
    return f"ggml-{descriptor.model_id}.bin"


def _entry(model_id: str, label: str, size_bytes: int, sha256: str) -> CatalogEntry:
    descriptor = ModelDescriptor(
        provider_id=PROVIDER_ID,
        model_id=model_id,
        display_name=f"whisper.cpp {label}",
        capabilities=_CAPABILITIES,
        source=SOURCE,
        revision=REVISION,
        # ponytail: CPU-only until a CUDA/Vulkan build is verified
        # (docs/whisper-cpp.md).
        profile=ProcessingProfile(
            name=ProcessingProfileName.FAST,
            device_preference=DevicePreference.CPU_ONLY,
            gpu_precisions=(),
            cpu_precision=ComputePrecision.INT8,
        ),
    )
    return CatalogEntry(
        descriptor,
        (ModelFile(model_filename(descriptor), size_bytes, sha256),),
        license="MIT",
        multilingual=True,
    )


_CATALOG = (
    _entry(
        "large-v3-turbo-q5_0",
        "Large v3 Turbo (q5_0)",
        574041195,
        "394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2",
    ),
    _entry(
        "large-v3-turbo-q8_0",
        "Large v3 Turbo (q8_0)",
        874188075,
        "317eb69c11673c9de1e1f0d459b253999804ec71ac4c23c17ecf5fbe24e259a1",
    ),
    _entry(
        "large-v3-turbo",
        "Large v3 Turbo",
        1624555275,
        "1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69",
    ),
    _entry(
        "small-q5_1",
        "Small (q5_1)",
        190085487,
        "ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb",
    ),
    _entry(
        "small",
        "Small",
        487601967,
        "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b",
    ),
    _entry(
        "base",
        "Base",
        147951465,
        "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe",
    ),
)


def whisper_cpp_catalog() -> tuple[CatalogEntry, ...]:
    """Every whisper.cpp model VOZ can install, pinned to a fixed revision."""
    return _CATALOG


class WhisperCppModelCatalog:
    """``ModelCatalog`` port adapter over the static pinned catalog."""

    def entries(self) -> tuple[CatalogEntry, ...]:
        return _CATALOG


__all__ = [
    "PROVIDER_ID",
    "REVISION",
    "SOURCE",
    "WhisperCppModelCatalog",
    "model_filename",
    "whisper_cpp_catalog",
]
