"""Cross-entity invariants that protect the domain boundary."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from voz.domain.entities.speaker import Speaker

_FORBIDDEN_DOMAIN_IMPORTS = frozenset({"fastapi", "pydantic", "sqlalchemy"})


def test_domain_does_not_import_framework_or_persistence_packages() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    domain_root = repository_root / "src" / "voz" / "domain"
    violations: list[str] = []

    for module_path in sorted(domain_root.rglob("*.py")):
        tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=module_path)
        for node in ast.walk(tree):
            imported_roots: tuple[str, ...]
            if isinstance(node, ast.Import):
                imported_roots = tuple(
                    alias.name.partition(".")[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_roots = (node.module.partition(".")[0],)
            else:
                continue

            forbidden = _FORBIDDEN_DOMAIN_IMPORTS.intersection(imported_roots)
            for package in sorted(forbidden):
                relative_path = module_path.relative_to(repository_root)
                violations.append(f"{relative_path}:{node.lineno} imports {package}")

    assert violations == []


def test_speaker_rename_rejects_updated_at_regression() -> None:
    """A new snapshot must not predate the snapshot it replaces."""

    created_at = datetime(2026, 9, 2, 12, tzinfo=UTC)
    current_updated_at = created_at + timedelta(hours=2)
    speaker = Speaker(
        uuid4(),
        "Profesor",
        "#123456",
        created_at=created_at,
        updated_at=current_updated_at,
    )

    with pytest.raises(ValueError, match="before current updated_at"):
        speaker.rename(
            "Docente",
            updated_at=current_updated_at - timedelta(hours=1),
        )
