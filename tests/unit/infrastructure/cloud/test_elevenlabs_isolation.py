"""S12.11: the ElevenLabs adapter must not leak into domain, application or UI."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).parents[4]
SRC = ROOT / "src/voz"
CLOUD = SRC / "infrastructure/cloud"
NEEDLES = ("elevenlabs", "eleven_labs", "eleven labs", "xi-api-key")


def _mentions(directory: Path, suffixes: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for path in sorted(directory.rglob("*")):
        if (
            path.is_file()
            and path.suffix in suffixes
            and "node_modules" not in path.parts
            and any(n in path.read_text(encoding="utf-8").lower() for n in NEEDLES)
        ):
            found.append(path.relative_to(ROOT).as_posix())
    return found


@pytest.mark.parametrize(
    ("directory", "suffixes"),
    [
        (SRC / "domain", (".py",)),
        (SRC / "application", (".py",)),
        (ROOT / "apps/web/src", (".ts", ".tsx", ".css", ".json")),
        (SRC / "static", (".js", ".css", ".html")),
    ],
)
def test_core_layers_and_ui_never_mention_elevenlabs(
    directory: Path, suffixes: tuple[str, ...]
) -> None:
    if not directory.exists():
        pytest.skip("directory not present")
    assert _mentions(directory, suffixes) == []


def test_the_adapter_lives_only_in_infrastructure_cloud() -> None:
    definitions = [
        path.relative_to(ROOT).as_posix()
        for path in sorted(SRC.rglob("*.py"))
        if "class ElevenLabsScribeProvider" in path.read_text(encoding="utf-8")
    ]

    assert definitions == ["src/voz/infrastructure/cloud/elevenlabs_scribe.py"]


def test_the_adapter_depends_only_inward() -> None:
    forbidden = ("fastapi", "sqlalchemy", "voz.interfaces", "voz.bootstrap")
    for path in sorted(CLOUD.glob("elevenlabs_*.py")):
        imports = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith(("import ", "from "))
        ]
        assert not [i for i in imports if any(f in i for f in forbidden)], path.name
