"""``shutil.disk_usage`` adapter for the application disk-space port."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path

from voz.application.ports.disk_space import DiskLocation


class ShutilDiskSpace:
    """Map logical locations to directories and ask the OS for free bytes."""

    def __init__(
        self,
        data_root: Path,
        *,
        locations: Mapping[DiskLocation, Path] | None = None,
    ) -> None:
        # ponytail: originals and derivatives share the data root today.
        overrides = locations or {}
        self._locations = {
            location: Path(overrides.get(location, data_root)).absolute()
            for location in DiskLocation
        }

    def free_bytes(self, location: DiskLocation) -> int:
        """Free bytes on the volume of the nearest existing ancestor directory."""
        path = self._locations[location]
        while not path.exists() and path != path.parent:
            path = path.parent
        return shutil.disk_usage(path).free


__all__ = ["ShutilDiskSpace"]
