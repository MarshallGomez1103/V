"""The suite never touches the real user profile (HOME / XDG / %LOCALAPPDATA%)."""

from __future__ import annotations

from pathlib import Path

import pytest

from voz.infrastructure.paths import resolve_voz_paths


def test_home_and_voz_paths_live_inside_pytest_temp_dir(
    tmp_path: Path,
) -> None:
    base = tmp_path.parent
    paths = resolve_voz_paths()
    for location in (Path.home(), paths.config, paths.data, paths.cache, paths.state):
        assert location.is_relative_to(base)


def test_test_can_still_override_xdg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    override = tmp_path / "custom"
    monkeypatch.setenv("XDG_DATA_HOME", str(override))
    assert resolve_voz_paths().data == override / "voz"
