"""Standalone local experiment CLI; resource controls live in its worker."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

import typer

from voz.application.edge_lab import (
    ERROR_MESSAGES,
    MAX_DEFINITION_BYTES,
    ExperimentDefinition,
    ExperimentExecutor,
    ExperimentResult,
    LabError,
    decode_definition,
)
from voz.infrastructure.constrained_process import ConstrainedProcess, outside_checkout
from voz.interfaces.cli.lab_results import register_results_command


def load_definition(path: Path) -> ExperimentDefinition:
    try:
        source = outside_checkout(path)
        if not source.is_file():
            raise LabError("lab_definition_unreadable")
        with source.open("rb") as handle:
            definition = decode_definition(handle.read(MAX_DEFINITION_BYTES + 1))
        directory = definition.model_directory
        return replace(
            definition,
            input_path=outside_checkout(
                source.parent / definition.input_path.expanduser()
            ),
            model_directory=outside_checkout(source.parent / directory.expanduser())
            if directory is not None
            else None,
        )
    except OSError as error:
        raise LabError("lab_definition_unreadable") from error


def create_lab_app(executor: ExperimentExecutor | None = None) -> typer.Typer:
    """Standalone composition point; tests can inject the process port."""
    app = typer.Typer(
        help="Run installed local models under child-only resource limits.",
        no_args_is_help=True,
        add_completion=False,
    )
    runner = executor if executor is not None else ConstrainedProcess()

    def _lab() -> None:
        """Run local experiments with an explicit resource profile."""

    def _run(definition: Path) -> None:
        """Execute a private JSON definition and emit a path-free JSON envelope."""
        try:
            result = runner.run(load_definition(definition))
        except LabError as error:
            result = ExperimentResult("failed", error.code)
        payload = asdict(result)
        payload["message"] = ERROR_MESSAGES[result.code] if result.code else None
        typer.echo(json.dumps(payload, ensure_ascii=False, allow_nan=False))
        code = (
            0
            if result.status == "completed"
            else {
                "lab_cancelled": 130,
                "lab_timeout": 124,
                "lab_invalid_definition": 2,
                "lab_definition_unreadable": 2,
                "lab_storage_unsafe": 2,
                "lab_limit_unsupported": 2,
                "lab_device_unavailable": 2,
            }.get(result.code or "", 1)
        )
        raise typer.Exit(code=code)

    app.callback()(_lab)
    app.command("run")(_run)
    register_results_command(app)
    return app


lab_app = create_lab_app()
