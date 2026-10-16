from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from voz.application.edge_lab import (
    MAX_DEFINITION_BYTES,
    LabError,
    decode_definition,
    definition_payload,
    parse_definition,
)


def definition_value() -> dict[str, object]:
    return {
        "schema_version": 1,
        "workload": "stt",
        "profile": {"device": "cpu", "cpu_mask": [0, 2], "address_space_bytes": 2**30},
        "model": {
            "engine": "faster-whisper",
            "model_id": "tiny",
            "directory": "models/tiny",
        },
        "input": {"path": "dataset", "language": "es"},
        "timeout_seconds": 10,
    }


def test_round_trip_has_explicit_controls_and_no_estimates() -> None:
    definition = parse_definition(definition_value())
    assert definition.profile.cpu_mask == (0, 2)
    assert definition.profile.address_space_bytes == 2**30
    assert definition.input_path == Path("dataset")
    assert (
        decode_definition(json.dumps(definition_payload(definition)).encode())
        == definition
    )


@pytest.mark.parametrize(
    "section,key,value",
    [
        (None, "argv", ["sh", "-c", "private payload"]),
        (None, "schema_version", True),
        (None, "schema_version", 2),
        (None, "workload", "shell"),
        (None, "timeout_seconds", False),
        (None, "timeout_seconds", -1),
        (None, "timeout_seconds", float("inf")),
        (None, "timeout_seconds", float("nan")),
        (None, "timeout_seconds", 10**400),
        ("profile", "cpu_mask", []),
        ("profile", "cpu_mask", [True]),
        ("profile", "cpu_mask", [1, 1]),
        ("profile", "cpu_mask", [-1]),
        ("profile", "address_space_bytes", True),
        ("profile", "address_space_bytes", 0),
        ("profile", "systemd", "yes"),
        ("profile", "device", "auto"),
        ("profile", "properties", {"ExecStart": "private payload"}),
        ("model", "engine", "openai"),
        ("model", "module", "private.module"),
        ("model", "directory", None),
        ("input", "path", "https://example.test/audio"),
        ("input", "path", "bad\x00path"),
        ("input", "speed", 1.0),
    ],
)
def test_rejects_unsafe_or_ambiguous_definition(
    section: str | None, key: str, value: object
) -> None:
    data = definition_value()
    if section is None:
        data[key] = value
    else:
        nested = data[section]
        assert isinstance(nested, dict)
        nested[key] = value
    with pytest.raises(LabError, match=r"^The experiment definition is invalid\.$"):
        parse_definition(data)


@pytest.mark.parametrize(
    "content",
    [
        b'{"schema_version":1,"schema_version":1}',
        b"[]",
        b"\xff",
        b"{}",
        b" " * (MAX_DEFINITION_BYTES + 1),
    ],
)
def test_decode_is_bounded_and_rejects_duplicate_keys(content: bytes) -> None:
    with pytest.raises(LabError) as raised:
        decode_definition(content)
    assert raised.value.code == "lab_invalid_definition"


def test_tts_requires_voice_and_store_model_not_a_directory() -> None:
    data = definition_value()
    data["workload"] = "tts"
    data["model"] = {"engine": "sherpa-onnx-tts", "model_id": "voice"}
    data["input"] = {"path": "text.txt", "voice_id": "0", "speed": 1.25}
    parsed = parse_definition(data)
    assert parsed.voice_id == "0" and parsed.speed == 1.25
    data["input"] = {"path": "text.txt"}
    with pytest.raises(LabError):
        parse_definition(data)


def test_application_boundary_is_stdlib_only() -> None:
    source = Path(__file__).parents[3] / "src/voz/application/edge_lab.py"
    tree = ast.parse(source.read_text())
    imports = [
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ]
    assert not any(
        name and name.startswith(("voz.infrastructure", "voz.interfaces", "typer"))
        for name in imports
    )
