"""Desktop and application-menu shortcut that opens VOZ from a source checkout."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class DesktopShortcutError(RuntimeError):
    """The shortcut could not be created; the message never carries host paths."""


@runtime_checkable
class DesktopShortcut(Protocol):
    def supported(self) -> bool:
        """Whether VOZ runs from a checkout with launchers on a supported OS."""
        ...

    def exists(self) -> bool:
        """Whether a shortcut created by VOZ is still there."""
        ...

    def location(self) -> str | None:
        """Where the shortcut is (home abbreviated as ``~``), or ``None``."""
        ...

    def create(self) -> str:
        """Create or recreate the shortcut; return its (abbreviated) location."""
        ...


__all__ = ["DesktopShortcut", "DesktopShortcutError"]
