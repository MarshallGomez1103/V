"""Unit tests for XDG path resolution."""

from pathlib import Path

from voz.infrastructure.paths import resolve_voz_paths


def test_resolve_voz_paths_uses_xdg_defaults() -> None:
    paths = resolve_voz_paths(environ={}, home=Path("/home/student"), platform="linux")

    assert paths.config == Path("/home/student/.config/voz")
    assert paths.data == Path("/home/student/.local/share/voz")
    assert paths.cache == Path("/home/student/.cache/voz")
    assert paths.state == Path("/home/student/.local/state/voz")


def test_resolve_voz_paths_honors_absolute_xdg_overrides(tmp_path: Path) -> None:
    paths = resolve_voz_paths(
        environ={
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
        },
        home=Path("/home/student"),
        platform="linux",
    )

    assert paths.config == tmp_path / "config" / "voz"
    assert paths.data == tmp_path / "data" / "voz"
    assert paths.cache == tmp_path / "cache" / "voz"
    assert paths.state == tmp_path / "state" / "voz"


def test_resolve_voz_paths_ignores_relative_or_empty_overrides() -> None:
    paths = resolve_voz_paths(
        environ={
            "XDG_CONFIG_HOME": "relative/config",
            "XDG_DATA_HOME": "",
        },
        home=Path("/home/student"),
        platform="linux",
    )

    assert paths.config == Path("/home/student/.config/voz")
    assert paths.data == Path("/home/student/.local/share/voz")


def test_windows_defaults_live_under_localappdata(tmp_path: Path) -> None:
    paths = resolve_voz_paths(
        environ={"LOCALAPPDATA": str(tmp_path / "Local")},
        home=Path("/Users/ana"),
        platform="win32",
    )

    root = tmp_path / "Local" / "voz"
    assert (paths.config, paths.data, paths.cache, paths.state) == (
        root / "config",
        root / "data",
        root / "cache",
        root / "state",
    )


def test_windows_without_localappdata_falls_back_to_home() -> None:
    paths = resolve_voz_paths(environ={}, home=Path("/Users/ana"), platform="win32")

    assert paths.data == Path("/Users/ana") / "AppData" / "Local" / "voz" / "data"


def test_macos_defaults_follow_library_conventions() -> None:
    paths = resolve_voz_paths(environ={}, home=Path("/Users/ana"), platform="darwin")

    support = Path("/Users/ana/Library/Application Support/voz")
    assert paths.config == support / "config"
    assert paths.data == support / "data"
    assert paths.state == support / "state"
    assert paths.cache == Path("/Users/ana/Library/Caches/voz")


def test_xdg_override_wins_on_every_platform(tmp_path: Path) -> None:
    override = tmp_path / "data"
    for platform in ("linux", "darwin", "win32"):
        paths = resolve_voz_paths(
            environ={"XDG_DATA_HOME": str(override)},
            home=Path("/Users/ana"),
            platform=platform,
        )
        assert paths.data == override / "voz"
