"""TTS benchmark for a fresh, already constrained Edge Lab worker (ADR-0011)."""

from __future__ import annotations

import math
import sys
import time
from collections.abc import Callable

from voz.application.edge_lab import (
    MAX_DEFINITION_BYTES,
    ExperimentDefinition,
    LabError,
)
from voz.application.tts_benchmark_metrics import calculate_tts_metrics


def peak_rss_observation(*, children: bool = False) -> tuple[float | None, str | None]:
    """Process high-water RSS or largest completed child; never a tree total."""
    if not (sys.platform.startswith("linux") or sys.platform == "darwin"):
        return None, "unsupported_platform"
    try:
        import resource
    except ImportError:
        return None, "resource_unavailable"
    try:
        who = resource.RUSAGE_CHILDREN if children else resource.RUSAGE_SELF
        peak = resource.getrusage(who).ru_maxrss
        mib = peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024
        if not math.isfinite(mib) or mib <= 0:
            return None, "no_valid_observation"
        return mib, None
    except (OSError, ValueError, OverflowError):
        return None, "read_failed"


def run_tts_benchmark(
    definition: ExperimentDefinition,
    *,
    clock: Callable[[], float] = time.perf_counter,
) -> tuple[dict[str, object], dict[str, object]]:
    """Render installed catalog TTS; the supervisor owns limits and cancellation."""
    from voz.application.text_chunking import plan_text_chunks
    from voz.infrastructure.constrained_process import outside_checkout
    from voz.infrastructure.paths import resolve_voz_paths
    from voz.infrastructure.tts.catalog import TTS_CATALOG
    from voz.infrastructure.tts.model_store import TtsModelStore
    from voz.infrastructure.tts.sherpa_provider import sherpa_tts_provider

    if definition.workload != "tts" or definition.engine != "sherpa-onnx-tts":
        raise LabError("lab_invalid_definition")
    if definition.profile.systemd:
        raise LabError("lab_limit_unsupported")
    if definition.profile.device != "cpu":
        raise LabError("lab_device_unavailable")
    entry = next(
        (entry for entry in TTS_CATALOG if entry.model_id == definition.model_id), None
    )
    if entry is None:
        raise LabError("lab_model_unavailable")
    data_root = outside_checkout(resolve_voz_paths().data)
    manifest = TtsModelStore(data_root=data_root).manifest(entry.model_id)
    if manifest is None:
        raise LabError("lab_model_unavailable")
    try:
        with outside_checkout(definition.input_path).open("rb") as handle:
            content = handle.read(MAX_DEFINITION_BYTES + 1)
        if len(content) > MAX_DEFINITION_BYTES:
            raise LabError("lab_input_unavailable")
        text = content.decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise LabError("lab_input_unavailable") from error
    if not text.strip() or len(text) > 20_000:
        raise LabError("lab_input_unavailable")
    threads = len(definition.profile.cpu_mask) if definition.profile.cpu_mask else 1
    provider = sherpa_tts_provider(
        {entry.model_id: manifest},
        num_threads=threads,
        timeout_seconds=definition.timeout_seconds,
    )
    frames = 0
    first_audio_seconds: float | None = None
    sample_rate: int | None = None
    try:
        try:
            chunks = plan_text_chunks(
                text, max_chars=provider.describe().max_chunk_chars
            )
            started = clock()
            for chunk in chunks:
                audio = provider.synthesize(
                    chunk.text,
                    model=entry.descriptor,
                    voice_id=definition.voice_id or "",
                    speed=definition.speed,
                )
                if first_audio_seconds is None:
                    first_audio_seconds = clock() - started
                if (
                    not audio.samples
                    or len(audio.samples) % audio.sample_format.width
                    or audio.sample_rate <= 0
                    or (sample_rate is not None and sample_rate != audio.sample_rate)
                ):
                    raise LabError("lab_worker_failed")
                sample_rate = audio.sample_rate
                frames += audio.frame_count
            if frames <= 0 or sample_rate is None or first_audio_seconds is None:
                raise LabError("lab_worker_failed")
        finally:
            provider.close()
        wall_seconds = clock() - started
        timing = calculate_tts_metrics(
            frames=frames,
            sample_rate=sample_rate,
            first_audio_seconds=first_audio_seconds,
            wall_seconds=wall_seconds,
        )
    except (LabError, MemoryError):
        raise
    except Exception as error:
        raise LabError("lab_worker_failed") from error
    memory: dict[str, object] = {}
    reasons: dict[str, str] = {}
    for name, children in (
        ("worker_peak_rss_mib", False),
        ("largest_child_peak_rss_mib", True),
    ):
        value, reason = peak_rss_observation(children=children)
        memory[name] = value
        if value is None:
            reasons[name] = reason or "unavailable"
    if reasons:
        memory["unavailable_reasons"] = reasons
    return {
        **timing,
        "input_characters": len(text),
        "frames": frames,
        "sample_rate": sample_rate,
        "chunks": len(chunks),
        "memory": memory,
        "methods": {
            "audio": "rendered chunks only; no inserted silence or saved audio",
            "ram": "separate worker and completed-child RSS peaks; not tree total",
            "first_audio": "first completed chunk returned; not sample streaming",
            "wall": "first synthesis call through provider close; preparation excluded",
            "throughput": (
                "rendered audio seconds / render wall seconds, including teardown"
            ),
        },
    }, {
        "model": {
            "engine": entry.descriptor.provider_id,
            "model_id": entry.model_id,
            "archive_sha256": entry.sha256,
        },
        "voice_id": definition.voice_id,
        "speed": definition.speed,
        "threads": threads,
    }
