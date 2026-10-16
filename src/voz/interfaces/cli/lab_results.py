"""Bounded private report loading and registration of ``lab compare``."""

from __future__ import annotations

from pathlib import Path

import typer

from voz.application.edge_lab import MAX_RESULT_BYTES, LabError
from voz.application.lab_comparison import ComparisonError, render_comparison
from voz.infrastructure.constrained_process import outside_checkout


def load_report(path: Path) -> bytes:
    """Read at most one MiB plus a sentinel, never from the source checkout."""
    try:
        source = outside_checkout(path)
        if not source.is_file():
            raise ComparisonError
        with source.open("rb") as handle:
            raw = handle.read(MAX_RESULT_BYTES + 1)
        if len(raw) > MAX_RESULT_BYTES:
            raise ComparisonError
        return raw
    except (OSError, ValueError, LabError) as error:
        raise ComparisonError from error


def register_results_command(app: typer.Typer) -> None:
    """Attach the report comparison command to an existing lab command group."""

    def compare(reports: list[Path]) -> None:
        """Compare local Edge Lab JSON reports as a measured-only Markdown table."""
        try:
            table = render_comparison([load_report(path) for path in reports])
        except ComparisonError as error:
            typer.echo(str(error), err=True)
            raise typer.Exit(code=2) from error
        typer.echo(table, nl=False)

    app.command("compare")(compare)
