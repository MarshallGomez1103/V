"""S15.09: one version, declared in pyproject and mirrored by ``voz.__version__``."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import voz

ROOT = Path(__file__).resolve().parents[2]


def test_package_version_matches_pyproject() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert voz.__version__ == pyproject["project"]["version"]


def test_version_is_semver_shaped() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[-+.][0-9A-Za-z.-]+)?", voz.__version__)
