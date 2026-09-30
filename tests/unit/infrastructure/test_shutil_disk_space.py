"""``ShutilDiskSpace`` adapter."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import NamedTuple

import pytest

from voz.application.ports.disk_space import DiskLocation, DiskSpacePort
from voz.infrastructure.disk_space import ShutilDiskSpace


class _Usage(NamedTuple):
    total: int
    used: int
    free: int


def test_reports_free_bytes_of_the_nearest_existing_ancestor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Path] = []

    def fake_usage(path: Path) -> _Usage:
        seen.append(Path(path))
        return _Usage(10, 4, 6)

    monkeypatch.setattr(shutil, "disk_usage", fake_usage)
    adapter = ShutilDiskSpace(tmp_path / "not" / "created" / "yet")

    assert isinstance(adapter, DiskSpacePort)
    assert adapter.free_bytes(DiskLocation.DERIVATIVES) == 6
    assert seen == [tmp_path]


def test_locations_can_be_overridden_individually(tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    adapter = ShutilDiskSpace(tmp_path, locations={DiskLocation.ORIGINALS: other})

    assert adapter.free_bytes(DiskLocation.ORIGINALS) > 0
    assert adapter.free_bytes(DiskLocation.DERIVATIVES) > 0
