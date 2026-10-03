"""Verified, resumable model download, local import and removal (no real network)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import pytest

from voz.application.ports.disk_space import DEFAULT_DISK_MARGIN_BYTES, DiskLocation
from voz.application.ports.model_installation import (
    ModelFile,
    ModelInstallationError,
    ModelInstallationFailureCode,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.infrastructure import model_storage
from voz.infrastructure.model_storage import FileSystemModelStore

_CODE = ModelInstallationFailureCode
_REVISION = "0123456789abcdef0123456789abcdef01234567"
_BIN = bytes(range(256)) * 32  # 8 KiB
_CFG = b'{"fixture": true}'
_PREFIX = f"/example/faster-whisper-fixture/resolve/{_REVISION}/"


def _descriptor(source: str = "example/faster-whisper-fixture") -> ModelDescriptor:
    return ModelDescriptor(
        provider_id="faster-whisper",
        model_id="fixture",
        display_name="Fixture model",
        capabilities=frozenset({ModelCapability.TRANSCRIPTION, ModelCapability.CPU}),
        source=source,
        revision=_REVISION,
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _files() -> tuple[ModelFile, ModelFile]:
    return (
        ModelFile("model.bin", len(_BIN), _sha(_BIN)),
        ModelFile("config.json", len(_CFG), None),  # non-LFS: no digest upstream
    )


@dataclass
class _Origin:
    url: str
    routes: dict[str, bytes] = field(default_factory=lambda: {})
    ranges: bool = True
    delay: float = 0.0
    truncate_once: set[str] = field(default_factory=lambda: set[str]())
    requests: list[tuple[str, str | None]] = field(default_factory=lambda: [])

    def serve_fixture(self) -> None:
        self.routes[_PREFIX + "model.bin"] = _BIN
        self.routes[_PREFIX + "config.json"] = _CFG


@pytest.fixture
def origin() -> Iterator[_Origin]:
    state = _Origin(url="")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            del format, args

        def do_GET(self) -> None:
            requested = self.headers.get("Range")
            state.requests.append((self.path, requested))
            if state.delay:
                time.sleep(state.delay)
            body = state.routes.get(self.path)
            if body is None:
                self.send_error(404)
                return
            start, status = 0, 200
            if requested and state.ranges:
                start = int(requested.removeprefix("bytes=").split("-")[0])
                if start >= len(body):
                    self.send_error(416)
                    return
                status = 206
            payload = body[start:]
            self.send_response(status)
            self.send_header("Content-Length", str(len(payload)))
            if status == 206:
                self.send_header(
                    "Content-Range", f"bytes {start}-{len(body) - 1}/{len(body)}"
                )
            self.end_headers()
            if self.path in state.truncate_once:
                state.truncate_once.discard(self.path)
                self.wfile.write(payload[: len(payload) // 2])
                self.wfile.flush()
                self.close_connection = True
                return
            self.wfile.write(payload)

    class Server(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request: Any, client_address: Any) -> None:
            del request, client_address

    server = Server(("127.0.0.1", 0), Handler)
    state.url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = Thread(
        target=lambda: server.serve_forever(poll_interval=0.01), daemon=True
    )
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture(autouse=True)
def small_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model_storage, "_BLOCK_BYTES", 1024)


class _FakeDisk:
    def __init__(self, free: int) -> None:
        self.free = free
        self.locations: list[DiskLocation] = []

    def free_bytes(self, location: DiskLocation) -> int:
        self.locations.append(location)
        return self.free


def _store(tmp_path: Path, **kwargs: Any) -> FileSystemModelStore:
    return FileSystemModelStore(
        data_root=tmp_path / "data",
        cache_root=tmp_path / "cache",
        clock=lambda: datetime(2026, 9, 30, tzinfo=UTC),
        **kwargs,
    )


def _staging(tmp_path: Path, store: FileSystemModelStore) -> Path:
    final = store._directory_for(_descriptor())  # pyright: ignore[reportPrivateUsage]
    return final.parent / f".download-{final.name}"


def _fail(code: ModelInstallationFailureCode, call: Any) -> ModelInstallationError:
    with pytest.raises(ModelInstallationError) as raised:
        call()
    assert raised.value.code is code
    for text in (raised.value.user_message, str(raised.value)):
        assert "/" not in text.replace("HTTP", "")  # no paths or URLs leak
    return raised.value


# --- download ---------------------------------------------------------------


def test_download_verifies_publishes_and_reports_progress(
    tmp_path: Path, origin: _Origin
) -> None:
    origin.serve_fixture()
    store = _store(tmp_path)
    ticks: list[tuple[int, int]] = []

    installation = store.download(
        _descriptor(),
        _files(),
        base_url=origin.url + "/",
        progress=lambda done, total: ticks.append((done, total)),
    )

    total = len(_BIN) + len(_CFG)
    assert installation.installed_at == datetime(2026, 9, 30, tzinfo=UTC)
    assert ticks[0] == (0, total) and ticks[-1] == (total, total)
    assert [t[0] for t in ticks] == sorted(t[0] for t in ticks)
    assert {t[1] for t in ticks} == {total}
    assert len(ticks) > 5  # block-granular, not one final tick
    assert [path for path, _ in origin.requests] == [
        _PREFIX + "model.bin",
        _PREFIX + "config.json",
    ]
    assert store.is_installed(_descriptor())
    resolved = store.resolve_path(_descriptor())
    assert (resolved / "model.bin").read_bytes() == _BIN
    assert (resolved / "config.json").read_bytes() == _CFG
    manifest = json.loads((resolved / ".voz-model.json").read_text())
    assert manifest["files"][0] == {
        "name": "model.bin",
        "size_bytes": len(_BIN),
        "sha256": _sha(_BIN),
    }
    assert sorted(p.name for p in resolved.parent.iterdir()) == [resolved.name]
    assert [d.identity for d in store.registered_descriptors()] == [
        _descriptor().identity
    ]


def test_download_of_installed_model_makes_no_requests(
    tmp_path: Path, origin: _Origin
) -> None:
    origin.serve_fixture()
    store = _store(tmp_path)
    store.download(_descriptor(), _files(), base_url=origin.url)
    origin.requests.clear()

    store.download(_descriptor(), _files(), base_url=origin.url)

    assert origin.requests == []


def test_cancel_keeps_partial_and_second_call_resumes_with_range(
    tmp_path: Path, origin: _Origin
) -> None:
    origin.serve_fixture()
    store = _store(tmp_path)
    seen = 0

    def progress(done: int, total: int) -> None:
        nonlocal seen
        del total
        seen = done

    _fail(
        _CODE.CANCELLED,
        lambda: store.download(
            _descriptor(),
            _files(),
            base_url=origin.url,
            progress=progress,
            cancelled=lambda: seen >= 2048,
        ),
    )
    partial = _staging(tmp_path, store) / "model.bin.part"
    kept = partial.stat().st_size
    assert 2048 <= kept < len(_BIN)
    assert not store.is_installed(_descriptor())

    ticks: list[int] = []
    store.download(
        _descriptor(),
        _files(),
        base_url=origin.url,
        progress=lambda done, total: ticks.append(done),
    )

    assert origin.requests[1] == (_PREFIX + "model.bin", f"bytes={kept}-")
    assert ticks[0] == kept  # progress resumes from what was already on disk
    assert (store.resolve_path(_descriptor()) / "model.bin").read_bytes() == _BIN


def test_resume_restarts_when_server_ignores_range(
    tmp_path: Path, origin: _Origin
) -> None:
    origin.serve_fixture()
    origin.ranges = False
    store = _store(tmp_path)
    staging = _staging(tmp_path, store)
    staging.mkdir(parents=True)
    (staging / "model.bin.part").write_bytes(_BIN[:3000])

    store.download(_descriptor(), _files(), base_url=origin.url)

    assert origin.requests[0][1] == "bytes=3000-"
    assert (store.resolve_path(_descriptor()) / "model.bin").read_bytes() == _BIN


def test_dropped_connection_is_a_network_error_and_resumable(
    tmp_path: Path, origin: _Origin
) -> None:
    origin.serve_fixture()
    origin.truncate_once.add(_PREFIX + "model.bin")
    store = _store(tmp_path)

    _fail(
        _CODE.NETWORK_ERROR,
        lambda: store.download(_descriptor(), _files(), base_url=origin.url),
    )
    kept = (_staging(tmp_path, store) / "model.bin.part").stat().st_size
    assert 0 < kept < len(_BIN)

    store.download(_descriptor(), _files(), base_url=origin.url)

    assert origin.requests[1][1] == f"bytes={kept}-"
    assert store.is_installed(_descriptor())


def test_checksum_mismatch_discards_part_and_retry_recovers(
    tmp_path: Path, origin: _Origin
) -> None:
    origin.serve_fixture()
    corrupt = bytes(reversed(_BIN))  # same size, different bytes
    origin.routes[_PREFIX + "model.bin"] = corrupt
    store = _store(tmp_path)

    _fail(
        _CODE.CHECKSUM_MISMATCH,
        lambda: store.download(_descriptor(), _files(), base_url=origin.url),
    )
    staging = _staging(tmp_path, store)
    assert not (staging / "model.bin.part").exists()
    assert not (staging / "model.bin").exists()
    assert not store.is_installed(_descriptor())

    origin.routes[_PREFIX + "model.bin"] = _BIN
    store.download(_descriptor(), _files(), base_url=origin.url)

    assert (store.resolve_path(_descriptor()) / "model.bin").read_bytes() == _BIN


@pytest.mark.parametrize("delta", [-1, 1], ids=["short", "long"])
def test_wrong_size_is_rejected_even_without_digest(
    tmp_path: Path, origin: _Origin, delta: int
) -> None:
    origin.serve_fixture()  # config.json has no digest: only its size can betray it
    origin.routes[_PREFIX + "config.json"] = _CFG[:-1] if delta < 0 else _CFG + b"!"
    store = _store(tmp_path)

    _fail(
        _CODE.CHECKSUM_MISMATCH,
        lambda: store.download(_descriptor(), _files(), base_url=origin.url),
    )

    assert not (_staging(tmp_path, store) / "config.json.part").exists()
    assert not store.is_installed(_descriptor())


def test_http_error_carries_status_without_leaking_urls(
    tmp_path: Path, origin: _Origin
) -> None:
    origin.serve_fixture()
    del origin.routes[_PREFIX + "config.json"]
    store = _store(tmp_path)

    error = _fail(
        _CODE.HTTP_ERROR,
        lambda: store.download(_descriptor(), _files(), base_url=origin.url),
    )

    assert error.status == 404
    assert "404" in error.user_message
    # the file that did download stays verified for the next attempt
    assert (_staging(tmp_path, store) / "model.bin").read_bytes() == _BIN


def test_network_timeout_is_typed(tmp_path: Path, origin: _Origin) -> None:
    origin.serve_fixture()
    origin.delay = 0.8
    store = _store(tmp_path, network_timeout_seconds=0.2)

    _fail(
        _CODE.NETWORK_ERROR,
        lambda: store.download(_descriptor(), _files(), base_url=origin.url),
    )


def test_unreachable_server_is_a_network_error(tmp_path: Path) -> None:
    store = _store(tmp_path, network_timeout_seconds=0.5)

    _fail(
        _CODE.NETWORK_ERROR,
        lambda: store.download(_descriptor(), _files(), base_url="http://127.0.0.1:9"),
    )


def test_oversized_part_and_corrupt_finished_file_are_redownloaded(
    tmp_path: Path, origin: _Origin
) -> None:
    origin.serve_fixture()
    store = _store(tmp_path)
    staging = _staging(tmp_path, store)
    staging.mkdir(parents=True)
    (staging / "model.bin.part").write_bytes(_BIN + b"junk")  # bigger than expected
    (staging / "config.json").write_bytes(b"x" * len(_CFG))  # wrong content, right size
    files = (_files()[0], ModelFile("config.json", len(_CFG), _sha(_CFG)))

    store.download(_descriptor(), files, base_url=origin.url)

    assert [r[1] for r in origin.requests] == [None, None]  # both from scratch
    resolved = store.resolve_path(_descriptor())
    assert (resolved / "model.bin").read_bytes() == _BIN
    assert (resolved / "config.json").read_bytes() == _CFG


def test_published_directory_with_wrong_size_is_not_installed_and_replaced(
    tmp_path: Path, origin: _Origin
) -> None:
    origin.serve_fixture()
    store = _store(tmp_path)
    store.download(_descriptor(), _files(), base_url=origin.url)
    published = store.resolve_path(_descriptor())
    (published / "model.bin").write_bytes(_BIN[:100])  # truncated after publication
    (published / "stale.txt").write_text("leftover")

    assert not store.is_installed(_descriptor())
    assert store.registered_descriptors() == ()
    with pytest.raises(Exception, match="not installed"):
        store.resolve_path(_descriptor())

    store.download(_descriptor(), _files(), base_url=origin.url)

    assert store.is_installed(_descriptor())
    assert (published / "model.bin").read_bytes() == _BIN
    assert not (published / "stale.txt").exists()


def test_download_requires_disk_space_for_pending_bytes_only(
    tmp_path: Path, origin: _Origin
) -> None:
    origin.serve_fixture()
    total = len(_BIN) + len(_CFG)
    disk = _FakeDisk(total + DEFAULT_DISK_MARGIN_BYTES - 1)
    store = _store(tmp_path, disk_space=disk)

    _fail(
        _CODE.DISK_SPACE_INSUFFICIENT,
        lambda: store.download(_descriptor(), _files(), base_url=origin.url),
    )
    assert origin.requests == []  # refused before touching the network
    assert disk.locations == [DiskLocation.DERIVATIVES]

    # 3000 bytes already on disk lower the requirement accordingly
    staging = _staging(tmp_path, store)
    (staging / "model.bin.part").write_bytes(_BIN[:3000])
    disk.free = total - 3000 + DEFAULT_DISK_MARGIN_BYTES
    store.download(_descriptor(), _files(), base_url=origin.url)

    assert store.is_installed(_descriptor())


def test_download_rejects_bad_inputs_before_any_io(
    tmp_path: Path, origin: _Origin
) -> None:
    store = _store(tmp_path)
    unpinned = ModelDescriptor(
        provider_id="faster-whisper",
        model_id="fixture",
        display_name="Fixture model",
        capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    )
    _fail(
        _CODE.PROVENANCE_REQUIRED,
        lambda: store.download(unpinned, _files(), base_url=origin.url),
    )
    _fail(
        _CODE.INVALID_SNAPSHOT,
        lambda: store.download(_descriptor(), (), base_url=origin.url),
    )
    _fail(
        _CODE.INVALID_SNAPSHOT,
        lambda: store.download(
            _descriptor(), (_files()[0], _files()[0]), base_url=origin.url
        ),
    )
    for bad in ("file:///etc", "ftp://example.org", "http://", "http://h/?q=1"):
        _fail(
            _CODE.DOWNLOAD_FAILED,
            lambda bad=bad: store.download(_descriptor(), _files(), base_url=bad),
        )
    assert origin.requests == []
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize(
    ("name", "size", "digest"),
    [
        ("", 1, None),
        ("..", 1, None),
        ("../x", 1, None),
        ("a/b", 1, None),
        ("a\\b", 1, None),
        ("..hidden", 1, None),
        (".voz-model.json", 1, None),
        ("x.part", 1, None),
        ("bad\nname", 1, None),
        ("ok.bin", 0, None),
        ("ok.bin", -5, None),
        ("ok.bin", 1, "ABC"),
        ("ok.bin", 1, "A" * 64),
    ],
)
def test_model_file_rejects_unsafe_values(
    name: str, size: int, digest: str | None
) -> None:
    with pytest.raises(ValueError):
        ModelFile(name, size, digest)


def test_model_file_accepts_dotfiles_and_lowercase_digests() -> None:
    ModelFile(".gitattributes", 10, None)
    ModelFile("model.bin", 10, "a" * 64)


# --- import_local_snapshot ----------------------------------------------------


def _hf_cache(root: Path) -> Path:
    """Hugging Face layout: ``snapshots/<rev>/x -> ../../blobs/<hash>``."""
    blobs = root / "models--example--fixture" / "blobs"
    snapshot = root / "models--example--fixture" / "snapshots" / _REVISION
    blobs.mkdir(parents=True)
    snapshot.mkdir(parents=True)
    for name, data in (("model.bin", _BIN), ("config.json", _CFG)):
        blob = blobs / _sha(data)
        blob.write_bytes(data)
        os.symlink(
            os.path.join("..", "..", "blobs", blob.name), snapshot / name
        )  # NTFS needs backslashes
    return snapshot


def _fingerprint(root: Path) -> list[tuple[str, int, int, bytes | None]]:
    rows: list[tuple[str, int, int, bytes | None]] = []
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        content = (
            path.read_bytes() if path.is_file() and not path.is_symlink() else None
        )
        rows.append(
            (str(path.relative_to(root)), info.st_mtime_ns, info.st_size, content)
        )
    return rows


def test_import_adopts_snapshot_without_modifying_it(tmp_path: Path) -> None:
    cache = tmp_path / "buzz-cache"
    snapshot = _hf_cache(cache)
    before = _fingerprint(cache)
    store = _store(tmp_path)
    ticks: list[tuple[int, int]] = []

    installation = store.import_local_snapshot(
        _descriptor(),
        _files(),
        snapshot,
        progress=lambda done, total: ticks.append((done, total)),
    )

    total = len(_BIN) + len(_CFG)
    assert installation.installed_at == datetime(2026, 9, 30, tzinfo=UTC)
    assert ticks[0] == (0, total) and ticks[-1] == (total, total)
    assert [t[0] for t in ticks] == sorted(t[0] for t in ticks)
    assert len(ticks) > 5  # hashed in blocks
    assert _fingerprint(cache) == before  # bytes, mtimes and layout untouched
    resolved = store.resolve_path(_descriptor())
    assert not (resolved / "model.bin").is_symlink()
    assert (resolved / "model.bin").read_bytes() == _BIN
    assert (resolved / "model.bin").stat().st_ino == (
        (cache / "models--example--fixture" / "blobs" / _sha(_BIN)).stat().st_ino
    )  # hardlinked: no second copy on the same filesystem
    assert store.is_installed(_descriptor())
    assert sorted(p.name for p in resolved.parent.iterdir()) == [resolved.name]


def test_import_falls_back_to_copy_when_hardlink_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "buzz-cache"
    snapshot = _hf_cache(cache)
    before = _fingerprint(cache)

    def no_link(*args: object, **kwargs: object) -> None:
        raise OSError(18, "cross-device")

    monkeypatch.setattr(os, "link", no_link)
    disk = _FakeDisk(10 * 1024**3)
    store = _store(tmp_path, disk_space=disk)

    store.import_local_snapshot(_descriptor(), _files(), snapshot)

    resolved = store.resolve_path(_descriptor())
    source_blob = cache / "models--example--fixture" / "blobs" / _sha(_BIN)
    assert (resolved / "model.bin").read_bytes() == _BIN
    assert (resolved / "model.bin").stat().st_ino != source_blob.stat().st_ino
    assert disk.locations  # copies are checked for space
    assert _fingerprint(cache) == before


def test_import_rejects_corrupt_snapshot_and_leaves_no_residue(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "buzz-cache"
    snapshot = _hf_cache(cache)
    before = _fingerprint(cache)
    store = _store(tmp_path)
    files = (ModelFile("model.bin", len(_BIN), "0" * 64), _files()[1])

    _fail(
        _CODE.CHECKSUM_MISMATCH,
        lambda: store.import_local_snapshot(_descriptor(), files, snapshot),
    )

    assert not store.is_installed(_descriptor())
    assert list((tmp_path / "data" / "models" / "faster-whisper").iterdir()) == []
    assert _fingerprint(cache) == before


def test_import_validates_snapshot_shape_before_writing(tmp_path: Path) -> None:
    cache = tmp_path / "buzz-cache"
    snapshot = _hf_cache(cache)
    store = _store(tmp_path)

    _fail(
        _CODE.INVALID_SNAPSHOT,
        lambda: store.import_local_snapshot(_descriptor(), _files(), cache / "nope"),
    )
    _fail(
        _CODE.INVALID_SNAPSHOT,
        lambda: store.import_local_snapshot(
            _descriptor(), (*_files(), ModelFile("vocab.txt", 5, None)), snapshot
        ),
    )
    _fail(
        _CODE.CHECKSUM_MISMATCH,
        lambda: store.import_local_snapshot(
            _descriptor(), (ModelFile("model.bin", 7, None),), snapshot
        ),
    )
    assert not (tmp_path / "data").exists()


def test_import_can_be_cancelled_and_cleans_up(tmp_path: Path) -> None:
    cache = tmp_path / "buzz-cache"
    snapshot = _hf_cache(cache)
    before = _fingerprint(cache)
    store = _store(tmp_path)
    seen = 0

    def progress(done: int, total: int) -> None:
        nonlocal seen
        del total
        seen = done

    _fail(
        _CODE.CANCELLED,
        lambda: store.import_local_snapshot(
            _descriptor(),
            _files(),
            snapshot,
            progress=progress,
            cancelled=lambda: seen >= 2048,
        ),
    )

    assert list((tmp_path / "data" / "models" / "faster-whisper").iterdir()) == []
    assert _fingerprint(cache) == before


# --- remove / disk_usage ------------------------------------------------------


def test_remove_and_disk_usage_are_scoped_to_the_descriptor(
    tmp_path: Path, origin: _Origin
) -> None:
    origin.serve_fixture()
    store = _store(tmp_path)
    other = _descriptor("example/other-model")
    assert store.disk_usage(_descriptor()) is None
    _fail(_CODE.NOT_INSTALLED, lambda: store.remove(_descriptor()))
    store.download(_descriptor(), _files(), base_url=origin.url)
    other_snapshot = tmp_path / "other"
    other_snapshot.mkdir()
    (other_snapshot / "model.bin").write_bytes(b"other-weights")
    store.import_local_snapshot(
        other, (ModelFile("model.bin", 13, None),), other_snapshot
    )
    directory = store.resolve_path(_descriptor())
    manifest_bytes = (directory / ".voz-model.json").stat().st_size

    assert store.disk_usage(_descriptor()) == len(_BIN) + len(_CFG) + manifest_bytes

    assert store.remove(_descriptor()) == len(_BIN) + len(_CFG) + manifest_bytes

    assert not directory.exists()
    assert not store.is_installed(_descriptor())
    assert store.disk_usage(_descriptor()) is None
    assert store.is_installed(other)
    assert list(directory.parent.glob(".remove-*")) == []
    _fail(_CODE.NOT_INSTALLED, lambda: store.remove(_descriptor()))


def test_remove_of_imported_model_keeps_source_and_reports_only_freed_bytes(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "buzz-cache"
    snapshot = _hf_cache(cache)
    before = _fingerprint(cache)
    store = _store(tmp_path)
    store.import_local_snapshot(_descriptor(), _files(), snapshot)
    directory = store.resolve_path(_descriptor())
    manifest_bytes = (directory / ".voz-model.json").stat().st_size
    before = _fingerprint(cache)

    freed = store.remove(_descriptor())

    assert freed == manifest_bytes  # hardlinked weights free nothing
    assert store.disk_usage(_descriptor()) is None
    assert _fingerprint(cache) == before


def test_hardlinked_import_reports_real_size_but_reclaims_only_its_own_files(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "buzz-cache"
    snapshot = _hf_cache(cache)
    store = _store(tmp_path)
    store.import_local_snapshot(_descriptor(), _files(), snapshot)
    directory = store.resolve_path(_descriptor())
    weights = sum(item.size_bytes for item in _files())

    used = store.disk_usage(_descriptor())
    reclaimable = store.reclaimable_usage(_descriptor())

    assert used is not None and used >= weights  # never "0 bytes"
    assert reclaimable == (directory / ".voz-model.json").stat().st_size
    assert store.reclaimable_usage(_descriptor("example/other-model")) is None


def test_remove_can_delete_a_directory_whose_files_were_damaged(
    tmp_path: Path, origin: _Origin
) -> None:
    origin.serve_fixture()
    store = _store(tmp_path)
    store.download(_descriptor(), _files(), base_url=origin.url)
    directory = store.resolve_path(_descriptor())
    (directory / "model.bin").write_bytes(b"short")

    assert not store.is_installed(_descriptor())
    assert store.disk_usage(_descriptor()) is not None
    assert store.remove(_descriptor()) > 0
    assert not directory.exists()
