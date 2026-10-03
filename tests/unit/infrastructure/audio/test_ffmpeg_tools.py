"""FFmpeg bootstrap: pinned download, checksum, cache and graceful failure."""

from __future__ import annotations

import hashlib
import io
import os
import zipfile
from pathlib import Path
from typing import BinaryIO

import pytest

from voz.infrastructure.audio import ffmpeg_tools
from voz.infrastructure.audio.ffmpeg_tools import ensure_ffmpeg, platform_key


def _zip_bytes(key: str) -> bytes:
    suffix = ".exe" if key == "win32" else ""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr(f"{key}/ffmpeg{suffix}", b"ffmpeg-binary")
        bundle.writestr(f"{key}/ffprobe{suffix}", b"ffprobe-binary")
        bundle.writestr("../escape.txt", b"must never be extracted")
    return buffer.getvalue()


class _Downloader:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.urls: list[str] = []

    def __call__(self, url: str, output: BinaryIO, announce: object) -> None:
        self.urls.append(url)
        output.write(self.payload)


@pytest.fixture(autouse=True)
def downloads_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VOZ_FFMPEG_AUTO_DOWNLOAD", raising=False)


@pytest.fixture
def pinned(monkeypatch: pytest.MonkeyPatch) -> bytes:
    payload = _zip_bytes("win32")
    monkeypatch.setitem(
        ffmpeg_tools._BUNDLES,  # pyright: ignore[reportPrivateUsage]
        "win32",
        ffmpeg_tools._Bundle(hashlib.sha256(payload).hexdigest(), 1),  # pyright: ignore[reportPrivateUsage]
    )
    monkeypatch.setenv("PATH", "base-path")
    return payload


def _none(_name: str) -> str | None:
    return None


def test_system_ffmpeg_is_preferred_and_nothing_is_downloaded(tmp_path: Path) -> None:
    download = _Downloader(b"")

    result = ensure_ffmpeg(
        cache_directory=tmp_path, download=download, which=lambda name: f"/bin/{name}"
    )

    assert result.status == "system"
    assert download.urls == []


def test_missing_tool_is_downloaded_verified_cached_and_put_on_path(
    tmp_path: Path, pinned: bytes
) -> None:
    download = _Downloader(pinned)
    messages: list[str] = []

    first = ensure_ffmpeg(
        cache_directory=tmp_path,
        announce=messages.append,
        download=download,
        which=_none,
        key="win32",
    )

    assert first.status == "downloaded"
    assert first.directory is not None
    assert (first.directory / "ffmpeg.exe").read_bytes() == b"ffmpeg-binary"
    assert (first.directory / "ffprobe.exe").read_bytes() == b"ffprobe-binary"
    assert os.environ["PATH"].split(os.pathsep)[0] == str(first.directory)
    assert "una sola vez" in messages[0]
    assert download.urls == [f"{ffmpeg_tools._BASE_URL}/win32.zip"]  # pyright: ignore[reportPrivateUsage]
    # Nothing but the final folder remains, and the zip-slip entry was ignored.
    assert [entry.name for entry in tmp_path.iterdir()] == [first.directory.name]
    assert not (tmp_path.parent / "escape.txt").exists()

    second = ensure_ffmpeg(
        cache_directory=tmp_path, download=download, which=_none, key="win32"
    )
    assert second.status == "cached"
    assert len(download.urls) == 1


def test_checksum_mismatch_is_rejected_without_leaving_files(
    tmp_path: Path, pinned: bytes
) -> None:
    result = ensure_ffmpeg(
        cache_directory=tmp_path,
        announce=lambda _message: None,
        download=_Downloader(pinned + b"tampered"),
        which=_none,
        key="win32",
    )

    assert result.status == "failed"
    assert "SHA-256" in result.message
    assert list(tmp_path.iterdir()) == []


def test_network_failure_reports_manual_install_options(tmp_path: Path) -> None:
    def offline(url: str, output: BinaryIO, announce: object) -> None:
        raise OSError("sin red")

    result = ensure_ffmpeg(
        cache_directory=tmp_path,
        announce=lambda _message: None,
        download=offline,
        which=_none,
        key="win32",
    )

    assert not result.available
    assert result.status == "failed"
    assert "winget install ffmpeg" in result.message
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("value", ["0", "false", "NO"])
def test_download_can_be_disabled(tmp_path: Path, value: str) -> None:
    download = _Downloader(b"")

    result = ensure_ffmpeg(
        cache_directory=tmp_path,
        download=download,
        which=_none,
        environ={"VOZ_FFMPEG_AUTO_DOWNLOAD": value},
        key="win32",
    )

    assert result.status == "missing"
    assert download.urls == []


def test_unsupported_platform_is_reported_not_raised(tmp_path: Path) -> None:
    result = ensure_ffmpeg(cache_directory=tmp_path, which=_none, key="plan9")

    assert result.status == "unsupported"


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("win32", "AMD64", "win32"),
        ("darwin", "arm64", "darwin_arm64"),
        ("darwin", "x86_64", "darwin"),
        ("linux", "x86_64", "linux"),
        ("linux", "aarch64", "linux_arm64"),
        ("freebsd14", "amd64", None),
    ],
)
def test_platform_key(system: str, machine: str, expected: str | None) -> None:
    assert platform_key(system, machine) == expected


def test_every_bundle_has_a_sha256_digest() -> None:
    for key, bundle in ffmpeg_tools._BUNDLES.items():  # pyright: ignore[reportPrivateUsage]
        assert len(bundle.sha256) == 64, key
