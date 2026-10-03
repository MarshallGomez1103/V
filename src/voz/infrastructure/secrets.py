"""Cloud API keys: environment first, then a 0600 TOML file in the XDG config dir."""

from __future__ import annotations

import contextlib
import json
import os
import re
import stat
import tempfile
import tomllib
from collections.abc import Mapping
from pathlib import Path

from voz.application.ports.provider_secrets import SecretsError, SecretsFailureCode

SECRETS_FILENAME = "secrets.toml"
_PROVIDER_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}", re.ASCII)
_KEY = re.compile(r"[\x21-\x7e]{1,512}", re.ASCII)


def _env_stem(provider_id: str) -> str:
    return re.sub(r"[^A-Z0-9]", "_", provider_id.upper())


class ProviderSecrets:
    """Resolve and persist API keys. Keys are never stored on the instance."""

    __slots__ = ("_config_dir", "_environ")

    def __init__(
        self, config_dir: Path, *, environ: Mapping[str, str] | None = None
    ) -> None:
        self._config_dir = config_dir
        self._environ = os.environ if environ is None else environ

    def __repr__(self) -> str:
        return "ProviderSecrets()"

    __str__ = __repr__

    @property
    def _file(self) -> Path:
        return self._config_dir / SECRETS_FILENAME

    def get(self, provider_id: str) -> str | None:
        """Return the key from env (VOZ_<ID>_API_KEY, <ID>_API_KEY) or the file."""
        stem = _env_stem(_checked_id(provider_id))
        for name in (f"VOZ_{stem}_API_KEY", f"{stem}_API_KEY"):
            value = self._environ.get(name, "").strip()
            if value:
                return value
        value = self._read_file().get(provider_id)
        return value if isinstance(value, str) and value else None

    def configured(self, provider_id: str) -> bool:
        """Never raises: an unusable secrets file simply means not configured."""
        try:
            return self.get(provider_id) is not None
        except SecretsError:
            return False

    def set(self, provider_id: str, key: str) -> None:
        _checked_id(provider_id)
        if _KEY.fullmatch(key) is None:
            raise SecretsError(
                SecretsFailureCode.KEY_INVALID,
                "The API key must be 1-512 printable characters without spaces.",
            )
        entries = self._read_file()
        entries[provider_id] = key
        self._write_file(entries)

    def delete(self, provider_id: str) -> None:
        """Remove the file entry; an environment variable is not ours to delete."""
        _checked_id(provider_id)
        entries = self._read_file()
        if entries.pop(provider_id, None) is None:
            return
        if entries:
            self._write_file(entries)
        else:
            with contextlib.suppress(FileNotFoundError):
                self._file.unlink()

    def _read_file(self) -> dict[str, object]:
        try:
            info = self._file.lstat()
        except FileNotFoundError:
            return {}
        except OSError as error:
            raise _invalid() from error
        # ponytail: Windows reports 0o666 for every file and has no POSIX modes;
        # the user-profile ACL is the protection there, so only POSIX is checked.
        group_or_world = info.st_mode & 0o077 if os.name != "nt" else 0
        if not stat.S_ISREG(info.st_mode) or group_or_world:
            raise SecretsError(
                SecretsFailureCode.FILE_INSECURE,
                "The secrets file must be a regular file with mode 0600.",
            )
        try:
            return dict(tomllib.loads(self._file.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
            raise _invalid() from error

    def _write_file(self, entries: Mapping[str, object]) -> None:
        body = "".join(
            f"{json.dumps(name)} = {json.dumps(value)}\n"
            for name, value in sorted(entries.items())
            if isinstance(value, str)
        )
        temporary: str | None = None
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            # mkstemp creates the file 0600, so the key is never world-readable.
            descriptor, temporary = tempfile.mkstemp(
                dir=self._config_dir, prefix=".secrets-"
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._file)
            temporary = None
        except OSError as error:
            raise SecretsError(
                SecretsFailureCode.WRITE_FAILED,
                "The secrets file could not be written.",
            ) from error
        finally:
            if temporary is not None:
                with contextlib.suppress(OSError):
                    os.unlink(temporary)


def _checked_id(provider_id: str) -> str:
    if _PROVIDER_ID.fullmatch(provider_id) is None:
        raise ValueError("provider_id must be a safe identifier")
    return provider_id


def _invalid() -> SecretsError:
    return SecretsError(
        SecretsFailureCode.FILE_INVALID, "The secrets file could not be read."
    )


__all__ = ["SECRETS_FILENAME", "ProviderSecrets"]
