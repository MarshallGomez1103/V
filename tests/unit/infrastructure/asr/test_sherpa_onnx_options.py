from __future__ import annotations

from pathlib import Path

import pytest

from voz.application.asr_device_selection import ComputeDevice, select_execution
from voz.application.ports.transcription import TranscriptionError
from voz.domain.entities.model_descriptor import ModelCapability
from voz.domain.entities.processing_profile import ComputePrecision
from voz.infrastructure.asr.sherpa_onnx_options import (
    SHERPA_ONNX_CAPABILITIES,
    SHERPA_ONNX_PROFILE,
    SherpaOnnxRuntimeProbe,
    whisper_files,
)


def test_probe_requires_no_model_and_selects_native_cpu_only() -> None:
    available = SherpaOnnxRuntimeProbe(module_available=lambda: True).probe(
        "sherpa-onnx-asr"
    )
    assert available.available and available.hardware is not None
    assert available.hardware.cpu_compute_types == frozenset({ComputePrecision.NATIVE})
    assert not available.hardware.cuda_compute_types
    execution = select_execution(SHERPA_ONNX_PROFILE, available.hardware)
    assert (
        execution.device is ComputeDevice.CPU
        and execution.precision is ComputePrecision.NATIVE
    )
    assert (
        frozenset({ModelCapability.TRANSCRIPTION, ModelCapability.CPU})
        == SHERPA_ONNX_CAPABILITIES
    )
    assert (
        not SherpaOnnxRuntimeProbe(module_available=lambda: False)
        .probe("sherpa-onnx-asr")
        .available
    )


def test_discovery_and_explicit_roles_require_regular_files(tmp_path: Path) -> None:
    for name in ("tiny-encoder.int8.onnx", "tiny-decoder.onnx", "tokens.txt"):
        (tmp_path / name).write_bytes(b"fake")
    files = whisper_files(tmp_path)
    assert files["encoder"].name == "tiny-encoder.int8.onnx"
    assert files["decoder"].name == "tiny-decoder.onnx"
    (tmp_path / "other-encoder.onnx").write_bytes(b"fake")
    with pytest.raises(TranscriptionError):
        whisper_files(tmp_path)
    assert (
        whisper_files(tmp_path, {key: path.name for key, path in files.items()})
        == files
    )


@pytest.mark.parametrize(
    "unsafe",
    [
        "../encoder.onnx",
        "/encoder.onnx",
        "C:/encoder.onnx",
        "a\\encoder.onnx",
        "encoder.py",
    ],
)
def test_rejects_unsafe_model_roles(tmp_path: Path, unsafe: str) -> None:
    with pytest.raises(TranscriptionError) as failure:
        whisper_files(
            tmp_path,
            {"encoder": unsafe, "decoder": "decoder.onnx", "tokens": "tokens.txt"},
        )
    assert unsafe not in failure.value.user_message


def test_rejects_model_links(tmp_path: Path) -> None:
    original = tmp_path / "original"
    original.write_bytes(b"safe")
    (tmp_path / "encoder.onnx").symlink_to(original)
    (tmp_path / "decoder.onnx").write_bytes(b"fake")
    (tmp_path / "tokens.txt").write_bytes(b"fake")
    with pytest.raises(TranscriptionError):
        whisper_files(tmp_path)
