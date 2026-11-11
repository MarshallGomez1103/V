"""One version, declared in pyproject and mirrored by every file that repeats it.

The tree carries the version in ``pyproject.toml``, ``voz.__version__``, the web
package and its lockfile (two places), the Flatpak metainfo release and the
changelog heading. A bump that forgets one of them fails here, naming the file.
"""

from __future__ import annotations

import json
import re
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import voz

ROOT = Path(__file__).resolve().parents[2]
_METAINFO = "packaging/flatpak/io.github.marshallgomez1103.v.metainfo.xml"


def _mirrored_versions(root: Path) -> dict[str, str]:
    """Version found in each file that must repeat the package version."""
    package = json.loads((root / "apps/web/package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "apps/web/package-lock.json").read_text(encoding="utf-8"))
    release = ET.parse(root / _METAINFO).getroot().find("./releases/release")
    return {
        "pyproject.toml": tomllib.loads(
            (root / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]["version"],
        "apps/web/package.json": package["version"],
        "apps/web/package-lock.json (top level)": lock["version"],
        'apps/web/package-lock.json (packages[""])': lock["packages"][""]["version"],
        f"{_METAINFO} (first <release>)": ""
        if release is None
        else release.get("version", ""),
    }


def _misaligned(root: Path, package_version: str) -> list[str]:
    """One line per file whose version differs from ``package_version``."""
    found = {"voz.__version__": package_version, **_mirrored_versions(root)}
    return [
        f"{name} declares {version!r}, expected {package_version!r}"
        for name, version in found.items()
        if version != package_version
    ]


def _changelog_has_entry(root: Path, version: str) -> bool:
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$"
    return re.search(heading, changelog, re.MULTILINE) is not None


def test_package_version_matches_pyproject() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert voz.__version__ == pyproject["project"]["version"]


def test_version_is_semver_shaped() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[-+.][0-9A-Za-z.-]+)?", voz.__version__)


def test_every_file_that_repeats_the_version_agrees() -> None:
    assert _misaligned(ROOT, voz.__version__) == []


def test_changelog_has_an_entry_for_the_current_version() -> None:
    assert _changelog_has_entry(ROOT, voz.__version__), (
        f"CHANGELOG.md has no '## [{voz.__version__}] - YYYY-MM-DD' heading"
    )


def _copy_tree(root: Path, version: str) -> None:
    """Write the smallest tree the guard reads, all at ``version``."""
    for relative in (
        "apps/web/package.json",
        "apps/web/package-lock.json",
        _METAINFO,
        "pyproject.toml",
    ):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
    lock = {"version": version, "packages": {"": {"version": version}}}
    (root / "apps/web/package.json").write_text(
        json.dumps({"version": version}), encoding="utf-8"
    )
    (root / "apps/web/package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    (root / _METAINFO).write_text(
        f'<component><releases><release version="{version}" date="2026-01-01"/>'
        "</releases></component>",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        f'[project]\nversion = "{version}"\n', encoding="utf-8"
    )
    (root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## [Unreleased]\n\n## [{version}] - 2026-01-01\n",
        encoding="utf-8",
    )


def test_guard_passes_on_an_aligned_tree(tmp_path: Path) -> None:
    _copy_tree(tmp_path, "1.2.3")

    assert _misaligned(tmp_path, "1.2.3") == []
    assert _changelog_has_entry(tmp_path, "1.2.3")


def test_guard_names_every_file_left_behind(tmp_path: Path) -> None:
    _copy_tree(tmp_path, "1.2.3")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nversion = "9.9.9"\n', encoding="utf-8"
    )

    problems = _misaligned(tmp_path, "1.2.3")

    assert len(problems) == 1
    assert problems[0].startswith("pyproject.toml declares '9.9.9'")
    # The other direction: the package bumped, every mirror left at 1.2.3.
    names = [line.split(" declares ")[0] for line in _misaligned(tmp_path, "9.9.9")]
    assert names == [
        "apps/web/package.json",
        "apps/web/package-lock.json (top level)",
        'apps/web/package-lock.json (packages[""])',
        f"{_METAINFO} (first <release>)",
    ]
    assert not _changelog_has_entry(tmp_path, "9.9.9")


def test_guard_flags_a_metainfo_without_releases(tmp_path: Path) -> None:
    _copy_tree(tmp_path, "1.2.3")
    (tmp_path / _METAINFO).write_text("<component/>", encoding="utf-8")

    assert [line.split(" declares ")[0] for line in _misaligned(tmp_path, "1.2.3")] == [
        f"{_METAINFO} (first <release>)"
    ]
