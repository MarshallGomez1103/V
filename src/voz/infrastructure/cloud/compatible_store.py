"""OpenAI-compatible endpoints in ``$XDG_CONFIG_HOME/voz/openai-compatible.json``.

Same protection as ``secrets.toml``: mode 0600, atomic replace, symlinks and
group/world access rejected. Keys are never written here (``ProviderSecrets``).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Final, cast

from voz.application.ports.compatible_endpoints import (
    CompatibleEndpoint,
    EndpointError,
    EndpointFailureCode,
)
from voz.infrastructure.secrets import (
    InsecureFileError,
    read_private_text,
    write_private_text,
)

ENDPOINTS_FILENAME: Final = "openai-compatible.json"
_FIELDS: Final = (
    "id",
    "name",
    "base_url",
    "stt_models",
    "tts_models",
    "tts_voices",
    "cloud_consent",
)


def _entry(raw: object) -> CompatibleEndpoint | None:
    if not isinstance(raw, dict):
        return None
    item = cast(dict[str, object], raw)
    values = {name: item.get(name) for name in _FIELDS}
    for name in ("stt_models", "tts_models", "tts_voices"):
        if isinstance(values[name], list):
            values[name] = tuple(cast(list[object], values[name]))
    try:
        return CompatibleEndpoint(**values)  # type: ignore[arg-type]
    except (EndpointError, TypeError):
        return None  # ponytail: a hand-edited bad entry is skipped, not fatal


class FileCompatibleEndpointStore:
    """Read on every call, so edits apply to the next request without restart."""

    def __init__(self, config_dir: Path) -> None:
        self._file = config_dir / ENDPOINTS_FILENAME
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return "FileCompatibleEndpointStore()"

    def list(self) -> tuple[CompatibleEndpoint, ...]:
        return self._read()

    def get(self, endpoint_id: str) -> CompatibleEndpoint | None:
        return next((item for item in self._read() if item.id == endpoint_id), None)

    def save(self, endpoint: CompatibleEndpoint) -> None:
        with self._lock:
            items = [item for item in self._read() if item.id != endpoint.id]
            self._write([*items, endpoint])

    def delete(self, endpoint_id: str) -> bool:
        with self._lock:
            items = self._read()
            kept = [item for item in items if item.id != endpoint_id]
            if len(kept) == len(items):
                return False
            self._write(kept)
            return True

    def _read(self) -> tuple[CompatibleEndpoint, ...]:
        try:
            text = read_private_text(self._file)
        except InsecureFileError:
            raise EndpointError(
                EndpointFailureCode.FILE_INSECURE,
                "The endpoints file must be a regular file with mode 0600.",
            ) from None
        except (OSError, UnicodeDecodeError):
            raise _unreadable() from None
        if text is None:
            return ()
        try:
            document = cast(object, json.loads(text))
        except ValueError:
            raise _unreadable() from None
        raw = (
            cast(dict[str, object], document).get("endpoints")
            if isinstance(document, dict)
            else None
        )
        if not isinstance(raw, list):
            raise _unreadable()
        found = (_entry(item) for item in cast(list[object], raw))
        return tuple(item for item in found if item is not None)

    def _write(self, items: list[CompatibleEndpoint]) -> None:
        body = {
            "version": 1,
            "endpoints": [
                {name: getattr(item, name) for name in _FIELDS} for item in items
            ],
        }
        try:
            write_private_text(self._file, json.dumps(body, indent=2) + "\n")
        except OSError:
            raise EndpointError(
                EndpointFailureCode.WRITE_FAILED,
                "The endpoints file could not be written.",
            ) from None


def _unreadable() -> EndpointError:
    return EndpointError(
        EndpointFailureCode.FILE_INVALID, "The endpoints file could not be read."
    )


__all__ = ["ENDPOINTS_FILENAME", "FileCompatibleEndpointStore"]
