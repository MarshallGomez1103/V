"""Unit tests for XDG path resolution."""

from pathlib import Path

from voz.infrastructure.paths import resolve_voz_paths


def test_resolve_voz_paths_uses_xdg_defaults() -> None:
    paths = resolve_voz_paths(environ={}, home=Path("/home/student"))

    assert paths.config == Path("/home/student/.config/voz")
    assert paths.data == Path("/home/student/.local/share/voz")
    assert paths.cache == Path("/home/student/.cache/voz")
    assert paths.state == Path("/home/student/.local/state/voz")


def test_resolve_voz_paths_honors_absolute_xdg_overrides() -> None:
    paths = resolve_voz_paths(
        environ={
            "XDG_CONFIG_HOME": "/runtime/config",
            "XDG_DATA_HOME": "/runtime/data",
            "XDG_CACHE_HOME": "/runtime/cache",
            "XDG_STATE_HOME": "/runtime/state",
        },
        home=Path("/home/student"),
    )

    assert paths.config == Path("/runtime/config/voz")
    assert paths.data == Path("/runtime/data/voz")
    assert paths.cache == Path("/runtime/cache/voz")
    assert paths.state == Path("/runtime/state/voz")


def test_resolve_voz_paths_ignores_relative_or_empty_overrides() -> None:
    paths = resolve_voz_paths(
        environ={
            "XDG_CONFIG_HOME": "relative/config",
            "XDG_DATA_HOME": "",
        },
        home=Path("/home/student"),
    )

    assert paths.config == Path("/home/student/.config/voz")
    assert paths.data == Path("/home/student/.local/share/voz")
