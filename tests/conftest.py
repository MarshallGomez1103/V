"""Shared pytest fixtures: platform modes and a network-free FFmpeg policy."""

from __future__ import annotations

import inspect
import os
import re
from collections.abc import Iterator

import pytest

from voz.infrastructure import safe_fs
from voz.infrastructure.audio import media_args

IS_WINDOWS = os.name == "nt"

# Tests that observe POSIX-only mechanics (symlinks, modes, dir_fd, /proc). A
# module opts back in with ``pytestmark = pytest.mark.windows_ok`` when its tests
# guard those details themselves.
_POSIX_ONLY = re.compile(
    r"symlink_to|os\.symlink|\.chmod\(|mkfifo|S_IMODE|dir_fd|fchmod|O_NOFOLLOW"
    r"|/proc/|getuid|st_mode|0o[0-7]{3}\b"
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if not IS_WINDOWS:
        return
    skip = pytest.mark.skip(
        reason="POSIX-only mechanics (symlinks, file modes, dir_fd, /proc)"
    )
    for item in items:
        function = getattr(item, "function", None)
        if function is None or item.get_closest_marker("windows_ok"):
            continue
        try:
            source = inspect.getsource(function)
        except (OSError, TypeError):
            continue
        if _POSIX_ONLY.search(source):
            item.add_marker(skip)


def _proc_path(descriptor: int) -> str:
    """Stand-in for GetFinalPathNameByHandle on Linux."""
    return os.readlink(f"/proc/self/fd/{descriptor}")


@pytest.fixture(autouse=True)
def no_ffmpeg_download(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never fetch FFmpeg; the dedicated tests inject a fake downloader."""
    monkeypatch.setenv("VOZ_FFMPEG_AUTO_DOWNLOAD", "0")


@pytest.fixture(
    params=["native", "portable-fd-args", "portable-path-args"],
)
def platform_mode(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    """Run a test on the native path and on both portable fallbacks.

    ``portable-*`` forces the no-``dir_fd`` filesystem layer (Windows behaviour)
    plus the macOS-style ``fd:N`` or Windows-style path hand-off to FFmpeg, so the
    code that only runs on those platforms is exercised on Linux too.
    """
    name = str(request.param)
    if name != "native":
        monkeypatch.setattr(safe_fs, "FORCE_PORTABLE", True)
        monkeypatch.setattr(
            media_args,
            "FORCE_MODE",
            "fd" if name == "portable-fd-args" else "path",
        )
    if name == "portable-path-args":
        if IS_WINDOWS:  # pragma: no cover - real implementation on Windows
            pass
        else:
            monkeypatch.setattr(media_args, "path_of_descriptor", _proc_path)
    yield name
