"""Per-platform locations for VOZ runtime data (XDG on Linux)."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

APPLICATION_DIRECTORY = "voz"


@dataclass(frozen=True, slots=True)
class VozPaths:
    """Resolved application directories outside the source checkout."""

    config: Path
    data: Path
    cache: Path
    state: Path


def _override(environ: Mapping[str, str], variable: str) -> Path | None:
    """Absolute ``$XDG_*`` override (honoured on every platform), else ``None``."""
    configured = environ.get(variable)
    if configured:
        candidate = Path(configured)
        if candidate.is_absolute():
            return candidate / APPLICATION_DIRECTORY
    return None


def _platform_defaults(
    environ: Mapping[str, str], home: Path, platform: str
) -> VozPaths:
    if platform == "win32":
        # One tree under %LOCALAPPDATA%\voz: easy to find, back up or delete.
        local = Path(environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        root = (local if local.is_absolute() else home / "AppData" / "Local") / (
            APPLICATION_DIRECTORY
        )
        return VozPaths(root / "config", root / "data", root / "cache", root / "state")
    if platform == "darwin":
        root = home / "Library" / "Application Support" / APPLICATION_DIRECTORY
        return VozPaths(
            root / "config",
            root / "data",
            home / "Library" / "Caches" / APPLICATION_DIRECTORY,
            root / "state",
        )
    return VozPaths(
        home / ".config" / APPLICATION_DIRECTORY,
        home / ".local" / "share" / APPLICATION_DIRECTORY,
        home / ".cache" / APPLICATION_DIRECTORY,
        home / ".local" / "state" / APPLICATION_DIRECTORY,
    )


def resolve_voz_paths(
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    platform: str | None = None,
) -> VozPaths:
    """Resolve VOZ paths: XDG on Linux, native conventions on Windows and macOS.

    Linux follows the XDG Base Directory specification. Windows keeps everything
    under ``%LOCALAPPDATA%\\voz`` and macOS under ``~/Library/Application
    Support/voz`` (cache in ``~/Library/Caches/voz``). An absolute ``XDG_*``
    variable overrides its own location on every platform (handy for tests and
    portable installs); empty or relative ones are ignored.
    """
    environment = os.environ if environ is None else environ
    home_directory = Path.home() if home is None else home
    defaults = _platform_defaults(
        environment, home_directory, sys.platform if platform is None else platform
    )
    return VozPaths(
        config=_override(environment, "XDG_CONFIG_HOME") or defaults.config,
        data=_override(environment, "XDG_DATA_HOME") or defaults.data,
        cache=_override(environment, "XDG_CACHE_HOME") or defaults.cache,
        state=_override(environment, "XDG_STATE_HOME") or defaults.state,
    )
