from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from voz.application.edge_lab import (
    ExperimentDefinition,
    ExperimentResult,
    LabCancellation,
)
from voz.interfaces.cli.lab import create_lab_app, load_definition


def definition_file(tmp_path: Path) -> Path:
    path = tmp_path / "experiment.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "workload": "stt",
                "profile": {"device": "cpu"},
                "model": {
                    "engine": "faster-whisper",
                    "model_id": "tiny",
                    "directory": "model",
                },
                "input": {"path": "dataset"},
            }
        )
    )
    return path


class FakeExecutor:
    def __init__(self, result: ExperimentResult) -> None:
        self.result = result
        self.definitions: list[ExperimentDefinition] = []

    def run(
        self,
        definition: ExperimentDefinition,
        cancellation: LabCancellation | None = None,
    ) -> ExperimentResult:
        self.definitions.append(definition)
        return self.result


def test_root_registration_snippet_and_relative_paths(tmp_path: Path) -> None:
    executor = FakeExecutor(ExperimentResult("completed", measured={"fixture": 1}))
    app = typer.Typer()
    app.add_typer(create_lab_app(executor), name="lab")
    result = CliRunner().invoke(app, ["lab", "run", str(definition_file(tmp_path))])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed" and payload["estimated"] == {}
    assert executor.definitions[0].input_path == tmp_path / "dataset"
    assert executor.definitions[0].model_directory == tmp_path / "model"
    assert str(tmp_path) not in result.stdout


@pytest.mark.parametrize(
    "status,code,exit_code",
    [
        ("cancelled", "lab_cancelled", 130),
        ("timed_out", "lab_timeout", 124),
        ("failed", "lab_model_unavailable", 1),
        ("failed", "lab_limit_unsupported", 2),
    ],
)
def test_safe_json_error_and_exit_codes(
    tmp_path: Path, status: str, code: str, exit_code: int
) -> None:
    executor = FakeExecutor(ExperimentResult(status, code))
    result = CliRunner().invoke(
        create_lab_app(executor), ["run", str(definition_file(tmp_path))]
    )
    assert result.exit_code == exit_code, result.output
    payload = json.loads(result.stdout)
    assert payload["code"] == code and payload["measured"] == {}
    assert str(tmp_path) not in result.stdout


def test_invalid_json_is_reported_without_echoing_private_content(
    tmp_path: Path,
) -> None:
    path = definition_file(tmp_path)
    path.write_text('{"argv": "private-command", "schema_version": NaN}')
    executor = FakeExecutor(ExperimentResult("completed", measured={"fixture": 1}))
    result = CliRunner().invoke(create_lab_app(executor), ["run", str(path)])
    assert result.exit_code == 2 and not executor.definitions
    assert json.loads(result.stdout)["code"] == "lab_invalid_definition"
    assert "private-command" not in result.stdout and str(path) not in result.stdout


def test_missing_definition_is_a_safe_error(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        create_lab_app(), ["run", str(tmp_path / "missing.json")]
    )
    assert result.exit_code == 2
    assert json.loads(result.stdout)["code"] == "lab_definition_unreadable"
    assert str(tmp_path) not in result.stdout


def test_definition_inside_checkout_is_refused() -> None:
    from voz.application.edge_lab import LabError

    with pytest.raises(LabError) as raised:
        load_definition(Path(__file__))
    assert raised.value.code == "lab_storage_unsafe"


@pytest.mark.skipif(os.name != "posix", reason="FIFO definition")
def test_non_regular_definition_is_rejected_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from voz.application.edge_lab import LabError

    path = tmp_path / "definition.pipe"
    os.mkfifo(path)

    def forbidden_open(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not block opening a FIFO")

    monkeypatch.setattr(Path, "open", forbidden_open)
    with pytest.raises(LabError) as raised:
        load_definition(path)
    assert raised.value.code == "lab_definition_unreadable"


@pytest.mark.skipif(os.name != "posix", reason="symlink loop")
def test_definition_resolution_error_does_not_leak_path(tmp_path: Path) -> None:
    from voz.application.edge_lab import LabError

    path = tmp_path / "loop"
    path.symlink_to(path)
    with pytest.raises(LabError) as raised:
        load_definition(path)
    assert str(tmp_path) not in str(raised.value)


def test_cli_expands_home_before_resolving_against_definition(tmp_path: Path) -> None:
    path = definition_file(tmp_path)
    data = json.loads(path.read_text())
    data["input"]["path"] = "~/dataset"
    data["model"]["directory"] = "~/model"
    path.write_text(json.dumps(data))
    definition = load_definition(path)
    assert definition.input_path == Path.home() / "dataset"
    assert definition.model_directory == Path.home() / "model"


def test_main_cli_registers_lab_run() -> None:
    from voz.interfaces.cli.main import app

    result = CliRunner().invoke(app, ["lab", "run", "--help"])
    assert result.exit_code == 0, result.output
    assert "definition" in result.output.lower()
