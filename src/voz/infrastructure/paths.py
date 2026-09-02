"""XDG-compliant locations for VOZ runtime data."""

from __future__ import annotations

import os
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


def _xdg_base(
    environ: Mapping[str, str],
    variable: str,
    fallback: Path,
) -> Path:
    configured = environ.get(variable)
    if configured:
        candidate = Path(configured)
        if candidate.is_absolute():
            return candidate
    return fallback


def resolve_voz_paths(
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> VozPaths:
    """Resolve VOZ paths according to the XDG Base Directory specification.

    Empty or relative XDG variables are invalid and therefore fall back to the
    conventional locations below ``home``.
    """
    environment = os.environ if environ is None else environ
    home_directory = Path.home() if home is None else home
    config_base = _xdg_base(
        environment,
        "XDG_CONFIG_HOME",
        home_directory / ".config",
    )
    data_base = _xdg_base(
        environment,
        "XDG_DATA_HOME",
        home_directory / ".local" / "share",
    )
    cache_base = _xdg_base(
        environment,
        "XDG_CACHE_HOME",
        home_directory / ".cache",
    )
    state_base = _xdg_base(
        environment,
        "XDG_STATE_HOME",
        home_directory / ".local" / "state",
    )

    return VozPaths(
        config=config_base / APPLICATION_DIRECTORY,
        data=data_base / APPLICATION_DIRECTORY,
        cache=cache_base / APPLICATION_DIRECTORY,
        state=state_base / APPLICATION_DIRECTORY,
    )
