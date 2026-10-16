"""Validated local experiments and the process execution port (ADR-0011)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, cast

MAX_DEFINITION_BYTES = 65_536
MAX_RESULT_BYTES = 1_048_576
ERROR_MESSAGES = {
    "lab_invalid_definition": "The experiment definition is invalid.",
    "lab_definition_unreadable": "The experiment definition could not be read.",
    "lab_input_unavailable": "The local input is missing or invalid.",
    "lab_model_unavailable": "The requested local model is not installed or known.",
    "lab_runtime_unavailable": "The local engine runtime is unavailable.",
    "lab_device_unavailable": "The requested device is not supported by Edge Lab.",
    "lab_limit_unsupported": "The requested resource control is unavailable.",
    "lab_limit_failed": "The requested resource control could not be verified.",
    "lab_storage_unsafe": "Experiment data must be outside the source checkout.",
    "lab_worker_failed": "The experiment worker failed.",
    "lab_invalid_result": "The experiment worker returned an invalid result.",
    "lab_allocation_failed": "The experiment could not allocate memory.",
    "lab_cancelled": "The experiment was cancelled.",
    "lab_timeout": "The experiment exceeded its deadline.",
}


class LabError(Exception):
    """Only fixed, path-free messages cross the experiment boundary."""

    def __init__(self, code: str) -> None:
        self.code = code if code in ERROR_MESSAGES else "lab_worker_failed"
        super().__init__(ERROR_MESSAGES[self.code])


@dataclass(frozen=True, slots=True)
class ResourceProfile:
    cpu_mask: tuple[int, ...] | None = None
    address_space_bytes: int | None = None
    device: str = "cpu"
    systemd: bool = False


@dataclass(frozen=True, slots=True)
class ExperimentDefinition:
    workload: str
    profile: ResourceProfile
    engine: str
    model_id: str
    input_path: Path
    model_directory: Path | None = None
    language: str | None = None
    voice_id: str | None = None
    speed: float = 1.0
    timeout_seconds: float = 120.0


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    status: str
    code: str | None = None
    measured: dict[str, object] = field(default_factory=dict[str, object])
    estimated: dict[str, object] = field(default_factory=dict[str, object])
    observations: dict[str, object] = field(default_factory=dict[str, object])
    constraints: dict[str, object] = field(default_factory=dict[str, object])
    schema_version: int = 1


class LabCancellation(Protocol):
    def is_cancelled(self) -> bool: ...


class ExperimentExecutor(Protocol):
    def run(
        self,
        definition: ExperimentDefinition,
        cancellation: LabCancellation | None = None,
    ) -> ExperimentResult: ...


def _object(value: object, allowed: set[str], required: set[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise LabError("lab_invalid_definition")
    data = cast(dict[str, object], value)
    if not required <= data.keys() <= allowed:
        raise LabError("lab_invalid_definition")
    return data


def _text(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 4096
        or any(ord(char) < 32 for char in value)
    ):
        raise LabError("lab_invalid_definition")
    return value


def _path(value: object) -> Path:
    text = _text(value)
    if "://" in text:
        raise LabError("lab_invalid_definition")
    return Path(text)


def _positive(value: object, maximum: float) -> float:
    if type(value) not in (int, float):
        raise LabError("lab_invalid_definition")
    try:
        number = float(cast(int | float, value))
    except OverflowError as error:
        raise LabError("lab_invalid_definition") from error
    if not math.isfinite(number) or not 0 < number <= maximum:
        raise LabError("lab_invalid_definition")
    return number


def parse_definition(value: object) -> ExperimentDefinition:
    data = _object(
        value,
        {"schema_version", "workload", "profile", "model", "input", "timeout_seconds"},
        {"schema_version", "workload", "profile", "model", "input"},
    )
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise LabError("lab_invalid_definition")
    workload = data["workload"]
    if workload not in ("stt", "tts"):
        raise LabError("lab_invalid_definition")
    profile = _object(
        data["profile"],
        {"cpu_mask", "address_space_bytes", "device", "systemd"},
        {"device"},
    )
    mask = profile.get("cpu_mask")
    cpu_mask: tuple[int, ...] | None = None
    if mask is not None:
        if not isinstance(mask, list):
            raise LabError("lab_invalid_definition")
        ids = cast(list[object], mask)
        if (
            not ids
            or len(ids) > 4096
            or any(type(cpu) is not int or cpu < 0 for cpu in ids)
        ):
            raise LabError("lab_invalid_definition")
        cpu_mask = tuple(cast(list[int], ids))
        if len(set(cpu_mask)) != len(cpu_mask):
            raise LabError("lab_invalid_definition")
    memory = profile.get("address_space_bytes")
    if memory is not None and (type(memory) is not int or not 0 < memory < 2**63):
        raise LabError("lab_invalid_definition")
    device = profile["device"]
    if device not in ("cpu", "cuda") or type(profile.get("systemd", False)) is not bool:
        raise LabError("lab_invalid_definition")
    model = _object(
        data["model"], {"engine", "model_id", "directory"}, {"engine", "model_id"}
    )
    engine = _text(model["engine"])
    if engine not in (
        {"faster-whisper", "whisper-cpp"} if workload == "stt" else {"sherpa-onnx-tts"}
    ):
        raise LabError("lab_invalid_definition")
    directory = (
        _path(model["directory"]) if model.get("directory") is not None else None
    )
    if (workload == "stt") != (directory is not None):
        raise LabError("lab_invalid_definition")
    inputs = _object(data["input"], {"path", "language", "voice_id", "speed"}, {"path"})
    voice = inputs.get("voice_id")
    if workload == "tts":
        voice = _text(voice)
    elif "voice_id" in inputs or "speed" in inputs:
        raise LabError("lab_invalid_definition")
    language = _text(inputs["language"]) if inputs.get("language") is not None else None
    if workload == "tts" and language is not None:
        raise LabError("lab_invalid_definition")
    speed = _positive(inputs.get("speed", 1.0), 2.0)
    if speed < 0.5:
        raise LabError("lab_invalid_definition")
    return ExperimentDefinition(
        workload=cast(str, workload),
        profile=ResourceProfile(
            cpu_mask,
            memory,
            cast(str, device),
            cast(bool, profile.get("systemd", False)),
        ),
        engine=engine,
        model_id=_text(model["model_id"]),
        input_path=_path(inputs["path"]),
        model_directory=directory,
        language=language,
        voice_id=cast(str | None, voice),
        speed=speed,
        timeout_seconds=_positive(data.get("timeout_seconds", 120.0), 86_400),
    )


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise LabError("lab_invalid_definition")
        result[key] = value
    return result


def decode_definition(content: bytes) -> ExperimentDefinition:
    try:
        if len(content) > MAX_DEFINITION_BYTES:
            raise LabError("lab_invalid_definition")
        value: object = json.loads(content, object_pairs_hook=_pairs)
        return parse_definition(value)
    except (ValueError, UnicodeError, OverflowError, RecursionError) as error:
        raise LabError("lab_invalid_definition") from error


def definition_payload(definition: ExperimentDefinition) -> dict[str, object]:
    """Private wire request; paths are never included in the public result."""
    from dataclasses import asdict

    return {
        "schema_version": 1,
        "workload": definition.workload,
        "profile": asdict(definition.profile),
        "model": {
            "engine": definition.engine,
            "model_id": definition.model_id,
            "directory": str(definition.model_directory)
            if definition.model_directory
            else None,
        },
        "input": {
            "path": str(definition.input_path),
            "language": definition.language,
            **(
                {"voice_id": definition.voice_id, "speed": definition.speed}
                if definition.workload == "tts"
                else {}
            ),
        },
        "timeout_seconds": definition.timeout_seconds,
    }
