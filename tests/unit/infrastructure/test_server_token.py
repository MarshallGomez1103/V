"""Server credentials are explicit private files, never diagnostic output."""

import os
from pathlib import Path

import pytest

from voz.infrastructure.server_token import (
    ServerTokenError,
    create_server_token,
    read_server_token,
)


def test_create_and_read_private_token_without_overwriting(tmp_path: Path) -> None:
    path = tmp_path / "config" / "server-token"
    create_server_token(path)
    token = read_server_token(path)
    assert len(token) >= 32
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ServerTokenError):
        create_server_token(path)
    assert read_server_token(path) == token


@pytest.mark.parametrize(
    "content", ["short-private-secret", "é" * 40, "x" * 514, "x" * 32 + " secret"]
)
def test_invalid_tokens_fail_without_echoing_content(
    tmp_path: Path, content: str
) -> None:
    path = tmp_path / "private-name"
    path.write_text(content)
    path.chmod(0o600)
    with pytest.raises(ServerTokenError) as raised:
        read_server_token(path)
    assert content not in str(raised.value)
    assert str(path) not in str(raised.value)


def test_missing_directory_symlink_and_permissive_files_are_rejected(
    tmp_path: Path,
) -> None:
    real = tmp_path / "token"
    create_server_token(real)
    link = tmp_path / "link"
    link.symlink_to(real)
    for path in (tmp_path / "missing", tmp_path, link):
        with pytest.raises(ServerTokenError):
            read_server_token(path)
    if os.name != "nt":
        real.chmod(0o644)
        with pytest.raises(ServerTokenError):
            read_server_token(real)


def test_token_reader_limits_the_file_size(tmp_path: Path) -> None:
    path = tmp_path / "large"
    path.write_bytes(b"x" * 10_000)
    path.chmod(0o600)
    with pytest.raises(ServerTokenError):
        read_server_token(path)


@pytest.mark.parametrize("ending", [b"", b"\n", b"\r\n"])
def test_token_file_accepts_standard_line_endings(
    tmp_path: Path, ending: bytes
) -> None:
    path = tmp_path / "token"
    path.write_bytes(b"x" * 32 + ending)
    path.chmod(0o600)
    assert read_server_token(path) == "x" * 32
