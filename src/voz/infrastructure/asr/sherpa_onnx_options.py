"""Experimental Whisper ONNX file layout and CPU runtime observations."""

from __future__ import annotations

import importlib
import re
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from voz.application.asr_device_selection import HardwareCapabilities
from voz.application.ports.transcription import (
    TranscriptionError,
    TranscriptionFailureCode,
)
from voz.application.ports.transcription_options import RuntimeAvailability
from voz.domain.entities.model_descriptor import ModelCapability
from voz.domain.entities.processing_profile import (
    ComputePrecision,
    DevicePreference,
    ProcessingProfile,
    ProcessingProfileName,
)

PROVIDER_ID = "sherpa-onnx-asr"
SHERPA_ONNX_CAPABILITIES = frozenset(
    {ModelCapability.TRANSCRIPTION, ModelCapability.CPU}
)
SHERPA_ONNX_PROFILE = ProcessingProfile(
    ProcessingProfileName.FAST, DevicePreference.CPU_ONLY, (), ComputePrecision.NATIVE
)


def runtime_available() -> bool:
    try:
        module = importlib.import_module("sherpa_onnx")
        return callable(
            getattr(getattr(module, "OfflineRecognizer", None), "from_whisper", None)
        )
    except (ImportError, OSError, ValueError):
        return False


@dataclass(frozen=True, slots=True)
class SherpaOnnxRuntimeProbe:
    module_available: Callable[[], bool] = runtime_available

    def probe(self, provider_id: str) -> RuntimeAvailability:
        available = provider_id == PROVIDER_ID and self.module_available()
        return RuntimeAvailability(
            available,
            hardware=HardwareCapabilities(
                cuda_compute_types=frozenset(),
                cpu_compute_types=frozenset({ComputePrecision.NATIVE}),
            )
            if available
            else None,
            capabilities=SHERPA_ONNX_CAPABILITIES,
        )


def observed_language(value: object) -> str | None:
    return (
        value
        if isinstance(value, str)
        and re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]{1,8})*", value, re.ASCII)
        else None
    )


def whisper_files(
    directory: Path, file_roles: Mapping[str, str] | None = None
) -> dict[str, Path]:
    """Resolve exactly one encoder/decoder/tokens set, never scripts or links."""
    try:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError
        if file_roles:
            if set(file_roles) != {"encoder", "decoder", "tokens"}:
                raise ValueError
            names = dict(file_roles)
        else:
            candidates: list[str] = []
            for count, path in enumerate(directory.iterdir()):
                if count >= 10_000:
                    raise ValueError
                candidates.append(path.name)
            names: dict[str, str] = {}
            for role in ("encoder", "decoder"):
                matches = [
                    name
                    for name in candidates
                    if re.fullmatch(r"(?:.*[-_])?" + role + r"(?:\.int8)?\.onnx", name)
                ]
                if len(matches) != 1:
                    raise ValueError
                names[role] = matches[0]
            names["tokens"] = "tokens.txt"
        result: dict[str, Path] = {}
        for role, name in names.items():
            relative = PurePosixPath(name)
            if (
                not name
                or len(name) > 512
                or relative.is_absolute()
                or relative.as_posix() != name
                or ".." in relative.parts
                or any(ch in name for ch in ("\\", ":"))
                or any(ord(ch) < 32 for ch in name)
                or (role != "tokens" and relative.suffix != ".onnx")
                or (role == "tokens" and relative.suffix != ".txt")
            ):
                raise ValueError
            path = directory / name
            for parent in relative.parents:
                if not stat.S_ISDIR((directory / parent).lstat().st_mode):
                    raise ValueError
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
                raise ValueError
            result[role] = path
        if len(set(result.values())) != 3:
            raise ValueError
        return result
    except (OSError, ValueError, TypeError):
        raise TranscriptionError(
            TranscriptionFailureCode.MODEL_NOT_INSTALLED,
            "The selected Whisper ONNX model files are not available.",
        ) from None
