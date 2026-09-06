"""Tests for explicit, side-effect-free local ASR composition."""

from dataclasses import replace
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest

from voz.application.asr_device_selection import (
    ComputeDevice,
    FallbackReason,
    HardwareCapabilities,
)
from voz.application.ports.transcription import (
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
)
from voz.bootstrap import create_local_asr_runtime
from voz.domain.entities.processing_profile import ComputePrecision
from voz.infrastructure.asr.catalog import faster_whisper_fast_descriptor
from voz.infrastructure.paths import VozPaths
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.schema import metadata


def test_local_asr_composition_is_explicit_and_does_not_download(
    tmp_path: Path,
) -> None:
    paths = VozPaths(
        config=tmp_path / "config",
        data=tmp_path / "data",
        cache=tmp_path / "cache",
        state=tmp_path / "state",
    )
    descriptor = faster_whisper_fast_descriptor(revision="a" * 40)

    runtime = create_local_asr_runtime(
        descriptor,
        paths=paths,
        hardware=HardwareCapabilities(
            cuda_compute_types=frozenset(),
            cpu_compute_types=frozenset({ComputePrecision.INT8}),
        ),
    )

    assert runtime.providers.provider_ids() == ("faster-whisper",)
    assert runtime.execution.device is ComputeDevice.CPU
    assert runtime.execution.fallback_reason is FallbackReason.CUDA_UNAVAILABLE
    assert not runtime.model_store.is_installed(descriptor)
    assert not paths.data.exists()
    assert not paths.cache.exists()


def test_local_asr_composition_wires_recoverable_sqlite_job(tmp_path: Path) -> None:
    paths = VozPaths(
        config=tmp_path / "config",
        data=tmp_path / "data",
        cache=tmp_path / "cache",
        state=tmp_path / "state",
    )
    descriptor = faster_whisper_fast_descriptor(revision="a" * 40)
    runtime = create_local_asr_runtime(
        descriptor,
        paths=paths,
        hardware=HardwareCapabilities(
            cuda_compute_types=frozenset(),
            cpu_compute_types=frozenset({ComputePrecision.INT8}),
        ),
    )
    engine = create_sqlite_engine((tmp_path / "voz.db").absolute())
    metadata.create_all(engine)

    use_case = runtime.recoverable_transcription(
        engine=engine,
        project_id=uuid4(),
        media_asset_id=uuid4(),
    )

    assert use_case.provider is runtime.providers.get("faster-whisper")
    engine.dispose()


def test_local_asr_runtime_is_bound_to_its_exact_descriptor(tmp_path: Path) -> None:
    paths = VozPaths(
        config=tmp_path / "config",
        data=tmp_path / "data",
        cache=tmp_path / "cache",
        state=tmp_path / "state",
    )
    descriptor = faster_whisper_fast_descriptor(revision="a" * 40)
    runtime = create_local_asr_runtime(
        descriptor,
        paths=paths,
        hardware=HardwareCapabilities(
            cuda_compute_types=frozenset(),
            cpu_compute_types=frozenset({ComputePrecision.INT8}),
        ),
    )

    with pytest.raises(TranscriptionError) as raised:
        runtime.providers.get("faster-whisper").transcribe(
            audio=BytesIO(b"not-read"),
            options=TranscriptionOptions(
                model=replace(descriptor, source="another/model")
            ),
        )

    assert raised.value.code is TranscriptionFailureCode.MODEL_NOT_INSTALLED


def test_local_asr_composition_rejects_another_provider(tmp_path: Path) -> None:
    descriptor = replace(
        faster_whisper_fast_descriptor(revision="a" * 40),
        provider_id="other-asr",
    )

    with pytest.raises(ValueError, match="Faster Whisper descriptor"):
        create_local_asr_runtime(
            descriptor,
            paths=VozPaths(
                config=tmp_path / "config",
                data=tmp_path / "data",
                cache=tmp_path / "cache",
                state=tmp_path / "state",
            ),
            hardware=HardwareCapabilities(
                cuda_compute_types=frozenset(),
                cpu_compute_types=frozenset({ComputePrecision.INT8}),
            ),
        )
