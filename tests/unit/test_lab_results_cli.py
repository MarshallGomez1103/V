from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from voz.application.edge_lab import MAX_RESULT_BYTES, ExperimentResult
from voz.application.lab_comparison import ComparisonError
from voz.interfaces.cli.lab_results import load_report, register_results_command


def comparison_app() -> typer.Typer:
    lab = typer.Typer()
    register_results_command(lab)
    app = typer.Typer()
    app.add_typer(lab, name="lab")
    return app


def report_file(tmp_path: Path, name: str, status: str = "completed") -> Path:
    path = tmp_path / name
    result = ExperimentResult(
        status,
        "lab_worker_failed" if status == "failed" else None,
        measured={"totals": {"rtf": 0.5}} if status == "completed" else {},
        observations={"model": {"model_id": "tiny"}},
    )
    path.write_text(json.dumps(asdict(result)))
    return path


def test_registration_snippet_compares_two_envelopes(tmp_path: Path) -> None:
    paths = [
        report_file(tmp_path, "one.json"),
        report_file(tmp_path, "two.json", "failed"),
    ]
    result = CliRunner().invoke(comparison_app(), ["lab", "compare", *map(str, paths)])
    assert result.exit_code == 0, result.output
    assert len(result.stdout.splitlines()) == 4
    assert "| completed | tiny |" in result.stdout
    assert "| failed | tiny |" in result.stdout
    assert not result.stderr
    assert str(tmp_path) not in result.stdout


@pytest.mark.parametrize(
    "status,code",
    [
        ("failed", "lab_worker_failed"),
        ("cancelled", "lab_cancelled"),
        ("timed_out", "lab_timeout"),
    ],
)
def test_unsuccessful_measurements_are_invalid_without_partial_output(
    tmp_path: Path, status: str, code: str
) -> None:
    valid = report_file(tmp_path, "valid.json")
    invalid = tmp_path / "invalid.json"
    invalid.write_text(
        json.dumps(
            asdict(ExperimentResult(status, code, measured={"totals": {"rtf": 0}}))
        )
    )
    result = CliRunner().invoke(
        comparison_app(), ["lab", "compare", str(valid), str(invalid)]
    )
    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr == "The experiment report is invalid or unavailable.\n"


@pytest.mark.parametrize(
    "content",
    ["bad-private-input", "NaN", "{}", " " * (MAX_RESULT_BYTES + 1)],
    # Short ids: the oversize payload as an id overflows Windows' 32767-char
    # limit for PYTEST_CURRENT_TEST and errors the test at setup.
    ids=["private-text", "nan", "empty-object", "oversize"],
)
def test_invalid_report_returns_two_without_partial_table_or_private_echo(
    tmp_path: Path, content: str
) -> None:
    first = report_file(tmp_path, "valid.json")
    invalid = tmp_path / "private-report.json"
    invalid.write_text(content)
    result = CliRunner().invoke(
        comparison_app(), ["lab", "compare", str(first), str(invalid)]
    )
    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr == "The experiment report is invalid or unavailable.\n"
    assert "bad-private-input" not in result.output
    assert str(tmp_path) not in result.output


@pytest.mark.parametrize("inside_checkout", [False, True])
def test_missing_or_checkout_report_is_a_safe_error(
    tmp_path: Path, inside_checkout: bool
) -> None:
    path = Path(__file__) if inside_checkout else tmp_path / "missing-private.json"
    result = CliRunner().invoke(comparison_app(), ["lab", "compare", str(path)])
    assert result.exit_code == 2 and result.stdout == ""
    assert str(path) not in result.output


def test_report_loader_expands_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = report_file(tmp_path, "report.json")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # what expanduser reads on Windows
    assert load_report(Path("~/report.json")) == path.read_bytes()


@pytest.mark.skipif(os.name != "posix", reason="FIFO and symlink behavior")
def test_nonregular_and_symlink_loop_are_refused_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fifo = tmp_path / "private.pipe"
    os.mkfifo(fifo)
    loop = tmp_path / "loop"
    loop.symlink_to(loop)

    def forbidden_open(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not block opening a FIFO")

    monkeypatch.setattr(Path, "open", forbidden_open)
    for path in (fifo, loop):
        with pytest.raises(ComparisonError):
            load_report(path)


def test_loader_uses_a_bounded_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = report_file(tmp_path, "report.json")
    reads: list[int] = []

    class FakeHandle:
        def __enter__(self) -> FakeHandle:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def read(self, size: int) -> bytes:
            reads.append(size)
            return b" " * size

    def fake_open(*_args: object, **_kwargs: object) -> FakeHandle:
        return FakeHandle()

    monkeypatch.setattr(Path, "open", fake_open)
    with pytest.raises(ComparisonError):
        load_report(path)
    assert reads == [MAX_RESULT_BYTES + 1]
