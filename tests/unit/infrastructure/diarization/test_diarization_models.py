"""Pinned diarization model install against a local HTTP server (no real network)."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from voz.application.ports.model_installation import (
    ModelInstallationError,
    ModelInstallationFailureCode,
)
from voz.infrastructure.diarization.models import (
    EMBEDDING_FILE,
    SEGMENTATION_FILE,
    DiarizationArtifact,
    DiarizationModelStore,
)

_CODE = ModelInstallationFailureCode
_SEGMENTATION = b"fake-segmentation-onnx" * 100
_EMBEDDING = b"fake-embedding-onnx" * 4000


def _archive(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:bz2") as bundle:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            bundle.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


_PREFIX = "sherpa-onnx-pyannote-segmentation-3-0/"
_TAR = _archive({_PREFIX + "model.onnx": _SEGMENTATION, _PREFIX + "LICENSE": b"MIT"})


class _Server:
    def __init__(self, routes: dict[str, bytes]) -> None:
        self.routes = routes
        self.requests: list[tuple[str, str | None]] = []
        self.cut_after: int | None = None
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                body = outer.routes.get(self.path)
                outer.requests.append((self.path, self.headers.get("Range")))
                if body is None:
                    self.send_error(404)
                    return
                start = 0
                range_header = self.headers.get("Range")
                if range_header:
                    start = int(range_header.removeprefix("bytes=").rstrip("-"))
                    self.send_response(206)
                    self.send_header(
                        "Content-Range", f"bytes {start}-{len(body) - 1}/{len(body)}"
                    )
                else:
                    self.send_response(200)
                self.send_header("Content-Length", str(len(body) - start))
                self.end_headers()
                chunk = body[start:]
                if outer.cut_after is not None:
                    self.wfile.write(chunk[: outer.cut_after])
                    self.wfile.flush()
                    self.close_connection = True
                    return
                self.wfile.write(chunk)

            def log_message(self, format: str, *args: object) -> None:
                return

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}{path}"


@pytest.fixture
def server() -> Iterator[_Server]:
    instance = _Server({"/seg.tar.bz2": _TAR, "/emb.onnx": _EMBEDDING})
    yield instance
    instance.httpd.shutdown()
    instance.httpd.server_close()


def _artifact(
    server: _Server, name: str, path: str, data: bytes, sha: bytes | None = None
) -> DiarizationArtifact:
    return DiarizationArtifact(
        name=name,
        url=server.url(path),
        size_bytes=len(data),
        sha256=hashlib.sha256(data if sha is None else sha).hexdigest(),
        license="test",
    )


def _store(
    tmp_path: Path, server: _Server, **overrides: bytes
) -> DiarizationModelStore:
    return DiarizationModelStore(
        data_root=tmp_path,
        segmentation=_artifact(server, "seg.tar.bz2", "/seg.tar.bz2", _TAR),
        embedding=_artifact(
            server, EMBEDDING_FILE, "/emb.onnx", _EMBEDDING, overrides.get("sha")
        ),
        network_timeout_seconds=1,
    )


def test_install_publishes_both_models_atomically(
    tmp_path: Path, server: _Server
) -> None:
    store = _store(tmp_path, server)
    assert not store.is_installed()
    progress: list[tuple[int, int]] = []

    paths = store.install(progress=lambda done, total: progress.append((done, total)))

    assert store.is_installed()
    assert paths.segmentation.read_bytes() == _SEGMENTATION
    assert paths.embedding.read_bytes() == _EMBEDDING
    assert paths.segmentation == tmp_path / "models/diarization" / SEGMENTATION_FILE
    assert (
        tmp_path / "models/diarization/LICENSE-pyannote-segmentation-3-0.txt"
    ).exists()
    assert not (tmp_path / "models/diarization.installing").exists()
    assert progress[-1][0] == progress[-1][1] == len(_TAR) + len(_EMBEDDING)
    assert [done for done, _ in progress] == sorted(done for done, _ in progress)
    manifest = json.loads(
        (tmp_path / "models/diarization/.voz-diarization.json").read_text()
    )
    assert set(manifest["files"]) >= {SEGMENTATION_FILE, EMBEDDING_FILE}


def test_second_install_is_a_no_op(tmp_path: Path, server: _Server) -> None:
    store = _store(tmp_path, server)
    store.install()
    count = len(server.requests)

    store.install()

    assert len(server.requests) == count


def test_cut_connection_is_a_network_error(tmp_path: Path, server: _Server) -> None:
    server.cut_after = 500

    with pytest.raises(ModelInstallationError) as failure:
        _store(tmp_path, server).install()

    assert failure.value.code == _CODE.NETWORK_ERROR
    assert not (tmp_path / "models/diarization").exists()


def test_partial_download_resumes_with_range(tmp_path: Path, server: _Server) -> None:
    store = _store(tmp_path, server)
    staging = tmp_path / "models/diarization.installing"
    staging.mkdir(parents=True)
    (staging / "seg.tar.bz2.part").write_bytes(_TAR[:100])

    store.install()

    assert ("/seg.tar.bz2", "bytes=100-") in server.requests
    assert store.is_installed()


def test_checksum_mismatch_discards_the_download(
    tmp_path: Path, server: _Server
) -> None:
    store = _store(tmp_path, server, sha=b"something else")

    with pytest.raises(ModelInstallationError) as failure:
        store.install()

    assert failure.value.code == _CODE.CHECKSUM_MISMATCH
    assert not store.is_installed()
    assert not (tmp_path / "models/diarization").exists()
    assert not list((tmp_path / "models/diarization.installing").glob("*.part"))


def test_cancellation_stops_before_publishing(tmp_path: Path, server: _Server) -> None:
    store = _store(tmp_path, server)

    with pytest.raises(ModelInstallationError) as failure:
        store.install(cancelled=lambda: True)

    assert failure.value.code == _CODE.CANCELLED
    assert not store.is_installed()


def test_http_error_carries_status(tmp_path: Path, server: _Server) -> None:
    server.routes.pop("/emb.onnx")

    with pytest.raises(ModelInstallationError) as failure:
        _store(tmp_path, server).install()

    assert failure.value.code == _CODE.HTTP_ERROR
    assert failure.value.status == 404


def test_archive_without_the_model_is_rejected(tmp_path: Path) -> None:
    bad = _archive({"other/file.txt": b"x"})
    server = _Server({"/seg.tar.bz2": bad, "/emb.onnx": _EMBEDDING})
    try:
        store = DiarizationModelStore(
            data_root=tmp_path,
            segmentation=_artifact(server, "seg.tar.bz2", "/seg.tar.bz2", bad),
            embedding=_artifact(server, EMBEDDING_FILE, "/emb.onnx", _EMBEDDING),
        )
        with pytest.raises(ModelInstallationError) as failure:
            store.install()
    finally:
        server.httpd.shutdown()
        server.httpd.server_close()

    assert failure.value.code == _CODE.INVALID_SNAPSHOT
    assert not store.is_installed()


def test_truncated_install_is_detected_and_repaired(
    tmp_path: Path, server: _Server
) -> None:
    store = _store(tmp_path, server)
    paths = store.install()
    paths.embedding.write_bytes(b"short")
    assert not store.is_installed()

    repaired = store.install()

    assert repaired.embedding.read_bytes() == _EMBEDDING


def test_remove_returns_freed_bytes(tmp_path: Path, server: _Server) -> None:
    store = _store(tmp_path, server)
    store.install()

    assert store.remove() >= len(_SEGMENTATION) + len(_EMBEDDING)
    assert not store.is_installed()
    assert store.remove() == 0
