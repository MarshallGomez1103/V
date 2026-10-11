"""S15.04: the built wheel and sdist ship everything VOZ needs at runtime."""

from __future__ import annotations

import re
import shutil
import subprocess
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PERSISTENCE = "voz/infrastructure/persistence"


@pytest.fixture(scope="module")
def dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build wheel + sdist from the checkout (a couple of seconds)."""
    uv = shutil.which("uv")
    if uv is None or not (ROOT / "pyproject.toml").is_file():
        pytest.skip("needs `uv` and a source checkout to build the artifacts")
    out = tmp_path_factory.mktemp("dist")
    result = subprocess.run(
        [uv, "build", "--out-dir", str(out)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if result.returncode != 0:
        pytest.skip(
            f"uv build failed (offline without a warm cache?): {result.stderr[-300:]}"
        )
    return out


@pytest.fixture(scope="module")
def wheel_names(dist: Path) -> set[str]:
    (wheel,) = dist.glob("*.whl")
    with zipfile.ZipFile(wheel) as archive:
        return set(archive.namelist())


@pytest.fixture(scope="module")
def sdist_names(dist: Path) -> set[str]:
    (sdist,) = dist.glob("*.tar.gz")
    with tarfile.open(sdist) as archive:
        # Drop the leading "<name>-<version>/" directory.
        return {name.split("/", 1)[1] for name in archive.getnames() if "/" in name}


def test_wheel_ships_frontend_bundle(dist: Path, wheel_names: set[str]) -> None:
    assert "voz/static/index.html" in wheel_names
    (wheel,) = dist.glob("*.whl")
    with zipfile.ZipFile(wheel) as archive:
        index = archive.read("voz/static/index.html").decode()
    referenced = re.findall(r"""(?:src|href)="/assets/([^"]+)""", index)
    assert referenced, "index.html references no hashed assets"
    for asset in referenced:
        assert f"voz/static/assets/{asset}" in wheel_names


def test_wheel_ships_alembic_and_every_migration(wheel_names: set[str]) -> None:
    assert f"{PERSISTENCE}/alembic.ini" in wheel_names
    assert f"{PERSISTENCE}/migrations/env.py" in wheel_names
    assert f"{PERSISTENCE}/migrations/script.py.mako" in wheel_names
    assert f"{PERSISTENCE}/migrations/versions/0004_segment_editing.py" in wheel_names
    for migration in (ROOT / "migrations" / "versions").glob("*.py"):
        assert f"{PERSISTENCE}/migrations/versions/{migration.name}" in wheel_names


def test_wheel_ships_every_source_module(wheel_names: set[str]) -> None:
    # Regression: .gitignore patterns such as `transcript.*` once made hatch drop
    # tracked sources (voz/domain/entities/transcript.py) from the wheel.
    sources = {
        path.relative_to(ROOT / "src").as_posix()
        for path in (ROOT / "src" / "voz").rglob("*.py")
        if "__pycache__" not in path.parts
    }
    assert "voz/domain/entities/transcript.py" in sources
    assert sources <= wheel_names
    assert not any(
        "__pycache__" in name or name.endswith(".pyc") for name in wheel_names
    )


def test_wheel_declares_console_script(dist: Path) -> None:
    (wheel,) = dist.glob("*.whl")
    with zipfile.ZipFile(wheel) as archive:
        entry_points = next(
            archive.read(name).decode()
            for name in archive.namelist()
            if name.endswith(".dist-info/entry_points.txt")
        )
    assert "voz = voz.interfaces.cli.main:main" in entry_points
    assert "v = voz.interfaces.cli.main:main" in entry_points.splitlines()


def test_pyproject_declares_v_and_voz_for_the_same_entrypoint() -> None:
    # Offline guard that does not need a build: `v` is the brand, `voz` the alias.
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    assert project["scripts"] == {
        "v": "voz.interfaces.cli.main:main",
        "voz": "voz.interfaces.cli.main:main",
    }
    assert project["name"] == "voz-transcriber"
    assert set(project["urls"].values()) >= {"https://github.com/MarshallGomez1103/V"}
    assert all(
        url.startswith("https://github.com/MarshallGomez1103/V")
        for url in project["urls"].values()
    )


def test_sdist_has_what_a_rebuild_needs(sdist_names: set[str]) -> None:
    required = {
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "alembic.ini",
        "src/voz/__init__.py",
        "src/voz/domain/entities/transcript.py",
        "src/voz/static/index.html",
        "migrations/env.py",
        "migrations/versions/0004_segment_editing.py",
        "apps/web/package.json",
        "apps/web/package-lock.json",
    }
    assert required <= sdist_names
    assert not any(
        "__pycache__" in name or name.endswith(".pyc") for name in sdist_names
    )
