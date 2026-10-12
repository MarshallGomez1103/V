"""sherpa-onnx TTS engine: a ``SubprocessSynthesisProvider`` over ``sherpa_worker``.

The server never imports ``sherpa_onnx``; each chunk runs in a child (ADR-0010).
Manifests come live from the store (``TtsModelStore.manifest``, V4-03);
``manifest_from_dir`` builds one from an extracted release tarball, reading
voices from the ONNX metadata in-process (a bounded protobuf scan, no native
code).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

from voz.application.ports.speech_synthesis import (
    SynthesisLocality,
    SynthesisProviderInfo,
)
from voz.infrastructure.tts import families
from voz.infrastructure.tts.subprocess_provider import (
    DEFAULT_TIMEOUT_SECONDS,
    ManifestSource,
    SubprocessSynthesisProvider,
    TtsModelManifest,
)

SHERPA_TTS_PROVIDER_ID: Final = "sherpa-onnx-tts"
WORKER_MODULE: Final = "voz.infrastructure.tts.sherpa_worker"
# V4-01: ~290 chars -> 15-20 s of audio in one pass; Piper renders it in
# ~1.5 s (RTF <= 0.09) and Kokoro int8 in ~16 s on one thread (RTF ~1). 400
# chars keeps the worst measured case near 25 s, far below the 120 s timeout,
# while the ~0.6-1.1 s model load per child stays a small share of each chunk.
MAX_CHUNK_CHARS: Final = 400


def sherpa_tts_info() -> SynthesisProviderInfo:
    return SynthesisProviderInfo(
        provider_id=SHERPA_TTS_PROVIDER_ID,
        display_name="sherpa-onnx",
        locality=SynthesisLocality.LOCAL,
        streaming=False,
        max_chunk_chars=MAX_CHUNK_CHARS,
    )


def sherpa_tts_provider(
    manifests: ManifestSource,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    num_threads: int | None = None,
) -> SubprocessSynthesisProvider:
    return SubprocessSynthesisProvider(
        info=sherpa_tts_info(),
        argv=[sys.executable, "-m", WORKER_MODULE],
        manifests=manifests,
        timeout_seconds=timeout_seconds,
        num_threads=num_threads,
    )


def manifest_from_dir(
    family: str,
    directory: Path,
    *,
    languages: tuple[str, ...] = (),
    ram_bytes: int | None = None,
) -> TtsModelManifest:
    """Manifest for an extracted model; raises ``families.ModelFilesError``."""
    files = families.discover_files(family, directory)
    disk = sum(p.stat().st_size for p in directory.rglob("*") if p.is_file())
    return TtsModelManifest(
        family=families.canonical_family(family),
        files=files,
        voices=families.read_voices(family, files, languages),
        languages=languages,
        ram_bytes=ram_bytes,
        disk_bytes=disk,
    )


__all__ = [
    "MAX_CHUNK_CHARS",
    "SHERPA_TTS_PROVIDER_ID",
    "WORKER_MODULE",
    "manifest_from_dir",
    "sherpa_tts_info",
    "sherpa_tts_provider",
]
