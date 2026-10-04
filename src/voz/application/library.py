"""List the library: projects with their recording, latest job and counts."""

from __future__ import annotations

import mimetypes
from collections.abc import Sequence
from dataclasses import dataclass, replace

from voz.application.ports.library import LibraryEntry, LibraryReader


def media_type_or_guess(media_type: str | None, filename: str | None) -> str | None:
    """The probed type, else the one the file extension implies (never invented)."""
    if media_type is not None or not filename:
        return media_type
    # ponytail: the extension is a hint only; the probe stays the source of truth.
    return mimetypes.guess_type(filename, strict=False)[0]


@dataclass(frozen=True, slots=True)
class ListLibrary:
    reader: LibraryReader

    def execute(self) -> Sequence[LibraryEntry]:
        """Most recent activity first; identity breaks ties deterministically."""
        entries = sorted(
            self.reader.entries(),
            key=lambda entry: (entry.activity_at, str(entry.project_id)),
            reverse=True,
        )
        return tuple(
            entry
            if entry.media is None
            else replace(
                entry,
                media=replace(
                    entry.media,
                    media_type=media_type_or_guess(
                        entry.media.media_type, entry.media.filename
                    ),
                ),
            )
            for entry in entries
        )


__all__ = ["ListLibrary", "media_type_or_guess"]
