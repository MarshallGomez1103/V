"""Desktop and application-menu shortcut that opens V (checkout or installed tool)."""

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
        """Whether a shortcut created by V is there and what it opens still exists."""
        ...

    def broken(self) -> bool:
        """Whether the shortcut is there but its target is gone (moved checkout)."""
        ...

    def location(self) -> str | None:
        """Where the shortcut is (home abbreviated as ``~``), or ``None``."""
        ...

    def create(self) -> str:
        """Create or recreate the shortcut; return its (abbreviated) location."""
        ...

    def refresh(self) -> bool:
        """Regenerate a broken or pre-V shortcut; never creates a missing one."""
        ...

    def remove(self) -> None:
        """Delete every copy of the shortcut and its marker (idempotent)."""
        ...


__all__ = ["DesktopShortcut", "DesktopShortcutError"]
