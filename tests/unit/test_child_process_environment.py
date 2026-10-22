"""Every process spawned by production code must pass an explicit ``env=``."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "src" / "voz"
SPAWNERS = {"Popen", "run", "call", "check_call", "check_output"}


def _spawn_calls_without_env(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = {"subprocess"}  # names bound to the subprocess module
    functions: set[str] = set()  # names bound to Popen/run/... directly
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "subprocess"
            )
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            functions.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name in SPAWNERS
            )
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        spawns = (
            isinstance(target, ast.Attribute)
            and target.attr in SPAWNERS
            and isinstance(target.value, ast.Name)
            and target.value.id in modules
        ) or (isinstance(target, ast.Name) and target.id in functions)
        if spawns and not any(keyword.arg == "env" for keyword in node.keywords):
            lines.append(node.lineno)
    return lines


@pytest.mark.parametrize("folder", ["infrastructure", "interfaces/cli"])
def test_every_spawn_passes_an_explicit_environment(folder: str) -> None:
    offenders = {
        f"{path.relative_to(SOURCE)}:{line}"
        for path in (SOURCE / folder).rglob("*.py")
        for line in _spawn_calls_without_env(path)
    }
    assert not offenders, f"spawns without env=: {sorted(offenders)}"


def test_the_scanner_sees_aliases_and_missing_env(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "import subprocess as sp\n"
        "from subprocess import run as go, Popen\n"
        "sp.run(['a'])\n"
        "go(['b'], env={})\n"
        "Popen(['c'])\n",
        encoding="utf-8",
    )
    assert _spawn_calls_without_env(sample) == [3, 5]
