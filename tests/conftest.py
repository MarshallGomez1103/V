"""Shared pytest fixtures: platform modes and a network-free FFmpeg policy."""

from __future__ import annotations

import inspect
import os
import re
from collections.abc import Iterator
from pathlib import Path

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


@pytest.fixture(autouse=True)
def isolated_user_dirs(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point HOME and every XDG/Windows profile variable at a throwaway directory
    under pytest's base temp (a sibling of ``tmp_path``, so tests that list
    ``tmp_path`` never see it).

    Autouse fixtures run before the test body, so tests that ``setenv`` these
    variables themselves still win. Keeps the owner's real data untouched.
    """
    home = tmp_path_factory.mktemp("home")
    for name, relative in {
        "HOME": "",
        "USERPROFILE": "",
        "APPDATA": "AppData/Roaming",
        "LOCALAPPDATA": "AppData/Local",
        "XDG_DATA_HOME": ".local/share",
        "XDG_CONFIG_HOME": ".config",
        "XDG_CACHE_HOME": ".cache",
        "XDG_STATE_HOME": ".local/state",
    }.items():
        target = home / relative
        target.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv(name, str(target))
    return home


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
    if name == "portable-fd-args" and IS_WINDOWS:
        pytest.skip("pass_fds does not exist on Windows; it uses the path mode")
    if name != "native":
        monkeypatch.setattr(safe_fs, "FORCE_PORTABLE", True)
        monkeypatch.setattr(
            media_args,
            "FORCE_MODE",
            "fd" if name == "portable-fd-args" else "path",
        )
    yield name
