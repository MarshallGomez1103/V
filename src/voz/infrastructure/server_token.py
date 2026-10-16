"""Bounded private files for explicitly enabled local server authentication."""

import os
import re
import secrets
import stat
from pathlib import Path

_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,512}", re.ASCII)


class ServerTokenError(Exception):
    code = "server_token_invalid"

    def __init__(self) -> None:
        super().__init__("The server token file is missing, insecure or invalid.")


def create_server_token(path: Path) -> None:
    """Create a new credential; existing files are never replaced."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(path, flags, 0o600), "w", encoding="ascii") as handle:
            handle.write(secrets.token_urlsafe(32) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        raise ServerTokenError() from None


def read_server_token(path: Path) -> str:
    """Read at most 514 bytes from an unchanged, regular private file."""
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise ServerTokenError()
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(path, flags), "rb") as handle:
            info = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or (before.st_dev, before.st_ino) != (info.st_dev, info.st_ino)
                or (os.name != "nt" and info.st_mode & 0o077)
                or not 32 <= info.st_size <= 514
            ):
                raise ServerTokenError()
            value = (
                handle.read(515).decode("ascii").removesuffix("\r\n").removesuffix("\n")
            )
        if _TOKEN.fullmatch(value) is None:
            raise ServerTokenError()
        return value
    except (OSError, UnicodeError, ValueError):
        raise ServerTokenError() from None
