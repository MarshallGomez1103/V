"""Remove the temporaries a killed process left below the data directory."""

from __future__ import annotations

import os
from pathlib import Path

from voz.infrastructure.safe_fs import DirectoryHandle, open_directory_chain

# Directory below ``projects/<id>`` -> (prefix, suffix) of the adapter's temporaries.
_TEMPORARIES = {
    "originals": (".import-", ".tmp"),
    "derivatives": (".normalize-", ".tmp.wav"),
}
_SYNTHESIS = "synthesis"  # synthesis/<job id>/ holds ``audio.wav`` and ``.audio-*.tmp``
_SYNTHESIS_TEMPORARY = (".audio-", ".tmp")


def _unlink_matching(directory: DirectoryHandle, prefix: str, suffix: str) -> None:
    for entry in directory.listdir():
        if entry.startswith(prefix) and entry.endswith(suffix):
            try:
                directory.unlink(entry)
            except OSError:
                continue  # retried at the next start


def discard_interrupted_temporaries(data_root: Path) -> None:
    """Unlink what imports, normalizations and renders create before they publish.

    A clean failure removes its own temporary; only a kill leaves one behind, and
    it may still be a second name for a finished file, so removing the name is
    always safe. A synthesis directory left empty is removed too. Call it before
    any such work starts: a live temporary looks exactly like an abandoned one.
    """
    try:
        projects = os.listdir(data_root / "projects")
    except OSError:
        projects = []
    for project in projects:
        for name, (prefix, suffix) in _TEMPORARIES.items():
            try:
                directory = open_directory_chain(
                    data_root, ("projects", project, name), create=False
                )
            except OSError:
                continue  # missing, or a link/odd entry: not ours to touch
            try:
                _unlink_matching(directory, prefix, suffix)
            finally:
                directory.close()
    _discard_synthesis(data_root)


def _discard_synthesis(data_root: Path) -> None:
    try:
        root = open_directory_chain(data_root, (_SYNTHESIS,), create=False)
    except OSError:
        return
    try:
        for job in root.listdir():
            try:
                directory = root.open_subdirectory(job)
            except OSError:
                continue  # not a plain directory
            try:
                _unlink_matching(directory, *_SYNTHESIS_TEMPORARY)
                empty = not directory.listdir()
            finally:
                directory.close()
            if empty:
                try:
                    root.rmdir(job)
                except OSError:
                    continue
    finally:
        root.close()
