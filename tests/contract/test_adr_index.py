"""``docs/adr/README.md`` lists every ADR with the status the ADR declares, and
every row of the index points at an ADR file that exists."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

ADR_DIR = Path(__file__).parents[2] / "docs/adr"
ADR_FILE = re.compile(r"^(\d{4})-.+\.md$")
STATUS_LINE = re.compile(r"^- Status:[ \t]*(.*?)[ \t]*$")
# `| [0001](0001-slug.md) | Title | Accepted | Roadmap |`
INDEX_ROW = re.compile(r"^\|\s*\[(\d{4})\]\(([^)\s]+)\)\s*\|(.*)\|\s*$")


def _read(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def adr_index_problems(adr_dir: Path) -> list[str]:
    """Every mismatch between the ADR files and their index, as ``file:line``
    messages. An empty list means the index is complete and consistent."""
    problems: list[str] = []
    statuses: dict[str, tuple[str, int]] = {}
    for path in sorted(adr_dir.glob("*.md")):
        if not ADR_FILE.match(path.name):
            continue
        status = next(
            (
                (match.group(1), number)
                for number, line in enumerate(_read(path), 1)
                if (match := STATUS_LINE.match(line))
            ),
            None,
        )
        if status is None or not status[0]:
            problems.append(f"{path.name}:1: no '- Status:' line")
            continue
        statuses[path.name] = status

    index = adr_dir / "README.md"
    listed: dict[str, int] = {}
    for number, line in enumerate(_read(index), 1):
        row = INDEX_ROW.match(line)
        if row is None:
            continue
        ident, target, rest = row.groups()
        where = f"{index.name}:{number}"
        cells = [cell.strip() for cell in rest.split("|")]
        if not (adr_dir / target).is_file():
            problems.append(f"{where}: row {ident} points at missing file {target}")
            continue
        if not target.startswith(f"{ident}-"):
            problems.append(f"{where}: row {ident} points at {target}")
        if target in listed:
            problems.append(
                f"{where}: {target} already listed at line {listed[target]}"
            )
        listed[target] = number
        declared = statuses.get(target)
        if declared is None:
            continue
        if len(cells) < 2 or cells[1] != declared[0]:
            shown = cells[1] if len(cells) > 1 else "(missing)"
            problems.append(
                f"{where}: {target} is '{shown}' in the index but "
                f"'{declared[0]}' in {target}:{declared[1]}"
            )

    problems.extend(
        f"{index.name}: {name} is not listed in the index"
        for name in statuses
        if name not in listed
    )
    return problems


def test_adr_index_matches_the_adrs() -> None:
    assert adr_index_problems(ADR_DIR) == []


def _copy(tmp_path: Path) -> Path:
    copy = tmp_path / "adr"
    shutil.copytree(ADR_DIR, copy)
    return copy


def test_a_status_that_differs_from_the_adr_is_reported(tmp_path: Path) -> None:
    adr = _copy(tmp_path)
    index = adr / "README.md"
    text = index.read_text(encoding="utf-8")
    assert "| Proposed |" in text
    index.write_text(text.replace("| Proposed |", "| Accepted |", 1), encoding="utf-8")
    problems = adr_index_problems(adr)
    assert len(problems) == 1
    assert "README.md:" in problems[0]
    assert "'Accepted' in the index but 'Proposed'" in problems[0]


def test_an_adr_missing_from_the_index_is_reported(tmp_path: Path) -> None:
    adr = _copy(tmp_path)
    (adr / "9999-new-decision.md").write_text(
        "# ADR-9999: New\n\n- Status: Proposed\n", encoding="utf-8"
    )
    assert adr_index_problems(adr) == [
        "README.md: 9999-new-decision.md is not listed in the index"
    ]


def test_a_row_for_a_missing_file_is_reported(tmp_path: Path) -> None:
    adr = _copy(tmp_path)
    (adr / "0001-modular-monolith.md").unlink()
    problems = adr_index_problems(adr)
    assert len(problems) == 1
    assert "points at missing file 0001-modular-monolith.md" in problems[0]


def test_an_adr_without_a_status_line_is_reported(tmp_path: Path) -> None:
    adr = tmp_path
    (adr / "0001-x.md").write_text("# ADR-0001\n", encoding="utf-8")
    (adr / "README.md").write_text(
        "| [0001](0001-x.md) | X | Accepted | - |\n", encoding="utf-8"
    )
    assert adr_index_problems(adr) == ["0001-x.md:1: no '- Status:' line"]


@pytest.mark.parametrize("declared", ["Accepted", "Proposed"])
def test_a_consistent_index_has_no_problems(tmp_path: Path, declared: str) -> None:
    (tmp_path / "0001-x.md").write_text(
        f"# ADR-0001\n\n- Status: {declared}\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text(
        f"| ADR | Title | Status | Roadmap |\n| --- | --- | --- | --- |\n"
        f"| [0001](0001-x.md) | X | {declared} | - |\n",
        encoding="utf-8",
    )
    assert adr_index_problems(tmp_path) == []
