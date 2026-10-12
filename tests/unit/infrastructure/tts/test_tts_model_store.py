"""TTS model install against a local HTTP server and a tar.bz2 built here."""

from __future__ import annotations

import hashlib
import io
import tarfile
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from voz.application.ports.model_installation import (
    ModelInstallationError,
    ModelInstallationFailureCode,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.voice import Voice
from voz.infrastructure.tts.catalog import TTS_PROVIDER_ID, TtsModelEntry
from voz.infrastructure.tts.model_store import TtsModelStore

_CODE = ModelInstallationFailureCode
_ROOT = "vits-test"
_GOOD = {
    f"{_ROOT}/test.onnx": b"onnx" * 500,
    f"{_ROOT}/tokens.txt": b"a 1\n",
    f"{_ROOT}/MODEL_CARD": b"card",
    f"{_ROOT}/espeak-ng-data/phontab": b"p" * 40,
    f"{_ROOT}/espeak-ng-data/voices/es": b"v" * 10,
    # Not wanted: never written to disk.
    f"{_ROOT}/README.md": b"run ./run.sh",
    f"{_ROOT}/run.sh": b"#!/bin/sh\ntouch /tmp/pwned\n",
    f"{_ROOT}/dict/big.bin": b"d" * 1000,
}


def _tar(
    members: dict[str, bytes], extra: Callable[[tarfile.TarFile], None] | None = None
) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:bz2") as bundle:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            bundle.addfile(info, io.BytesIO(data))
        if extra is not None:
            extra(bundle)
    return buffer.getvalue()


def _link(
    name: str, target: str, kind: bytes = tarfile.SYMTYPE
) -> Callable[[tarfile.TarFile], None]:
    def add(bundle: tarfile.TarFile) -> None:
        info = tarfile.TarInfo(name)
        info.type, info.linkname = kind, target
        bundle.addfile(info)

    return add


class _Server:
    def __init__(self, routes: dict[str, bytes]) -> None:
        self.routes = routes
        self.requests: list[str | None] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                body = outer.routes.get(self.path)
                outer.requests.append(self.headers.get("Range"))
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
                self.wfile.write(body[start:])

            def log_message(self, format: str, *args: object) -> None:
                return

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}{path}"


@pytest.fixture
def server() -> Iterator[_Server]:
    instance = _Server({})
    yield instance
    instance.httpd.shutdown()
    instance.httpd.server_close()


def _entry(server: _Server, data: bytes, *, sha: bytes | None = None) -> TtsModelEntry:
    server.routes["/m.tar.bz2"] = data
    return TtsModelEntry(
        descriptor=ModelDescriptor(
            provider_id=TTS_PROVIDER_ID,
            model_id="test-voice",
            display_name="Test voice",
            capabilities=frozenset({ModelCapability.SYNTHESIS, ModelCapability.CPU}),
        ),
        family="vits",
        archive_name="vits-test.tar.bz2",
        url=server.url("/m.tar.bz2"),
        size_bytes=len(data),
        sha256=hashlib.sha256(data if sha is None else sha).hexdigest(),
        root=_ROOT,
        files=(("model", "test.onnx"), ("tokens", "tokens.txt")),
        directories=(("data_dir", "espeak-ng-data"),),
        languages=("es",),
        voices=(Voice("0", "Test", ("es",)),),
        sample_rate=22_050,
        license="test",
        ram_bytes=1000,
    )


def _store(tmp_path: Path, entry: TtsModelEntry) -> TtsModelStore:
    return TtsModelStore(
        data_root=tmp_path / "data", catalog=(entry,), network_timeout_seconds=1
    )


def _install_error(store: TtsModelStore, **kwargs: object) -> ModelInstallationError:
    with pytest.raises(ModelInstallationError) as caught:
        store.install("test-voice", **kwargs)  # type: ignore[arg-type]
    return caught.value


def _tree(tmp_path: Path) -> set[str]:
    return {str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")}


def test_install_extracts_only_the_wanted_files_and_builds_the_manifest(
    tmp_path: Path, server: _Server
) -> None:
    entry = _entry(server, _tar(_GOOD))
    store = _store(tmp_path, entry)
    assert not store.is_installed("test-voice")
    assert store.manifest("test-voice") is None
    progress: list[tuple[int, int]] = []

    manifest = store.install(
        "test-voice", progress=lambda done, total: progress.append((done, total))
    )

    directory = tmp_path / "data/models/tts/test-voice"
    assert store.is_installed("test-voice")
    assert manifest.family == "vits"
    assert manifest.files == {
        "model": directory / "test.onnx",
        "tokens": directory / "tokens.txt",
        "data_dir": directory / "espeak-ng-data/phontab",
    }
    assert (directory / "test.onnx").read_bytes() == _GOOD[f"{_ROOT}/test.onnx"]
    assert all(path.is_file() for path in manifest.files.values())  # engine rule
    assert (directory / "espeak-ng-data/voices/es").is_file()
    assert (directory / "MODEL_CARD").read_bytes() == b"card"
    assert not (directory / "run.sh").exists()
    assert not (directory / "README.md").exists()
    assert not (directory / "dict").exists()
    assert manifest.voices == entry.voices and manifest.languages == ("es",)
    assert manifest.ram_bytes == 1000
    assert manifest.disk_bytes == store.disk_usage("test-voice")
    assert (manifest.disk_bytes or 0) > 2000
    assert progress[-1] == (entry.size_bytes, entry.size_bytes)
    assert all(done <= total for done, total in progress)
    assert not (tmp_path / "data/models/tts/test-voice.installing").exists()
    assert set(store.manifests()) == {"test-voice"}

    server.requests.clear()
    store.install("test-voice")  # already installed: no network
    assert server.requests == []


def test_a_bad_checksum_is_rejected_before_anything_is_extracted(
    tmp_path: Path, server: _Server
) -> None:
    entry = _entry(server, _tar(_GOOD), sha=b"another archive")
    store = _store(tmp_path, entry)

    assert _install_error(store).code is _CODE.CHECKSUM_MISMATCH

    assert not store.is_installed("test-voice")
    models = tmp_path / "data/models/tts"
    assert not (models / "test-voice").exists()
    assert not (models / "test-voice.installing/model").exists()
    assert not list(models.rglob("*.onnx"))
    assert not list(models.rglob("*.part"))


def test_a_wrong_size_is_a_download_error_not_an_install(
    tmp_path: Path, server: _Server
) -> None:
    data = _tar(_GOOD)
    entry = _entry(server, data)
    server.routes["/m.tar.bz2"] = data + b"junk"  # longer than pinned

    error = _install_error(_store(tmp_path, entry))

    assert error.code is _CODE.CHECKSUM_MISMATCH
    assert not (tmp_path / "data/models/tts/test-voice").exists()


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda: _tar({**_GOOD, f"{_ROOT}/../evil": b"x"}), id="dotdot"),
        pytest.param(lambda: _tar({**_GOOD, "../evil": b"x"}), id="dotdot-top"),
        pytest.param(lambda: _tar({**_GOOD, "/tmp/evil-abs": b"x"}), id="absolute"),
        pytest.param(lambda: _tar({**_GOOD, f"{_ROOT}\\..\\evil": b"x"}), id="winsep"),
        pytest.param(
            lambda: _tar(
                {k: v for k, v in _GOOD.items() if not k.endswith("test.onnx")},
                _link(f"{_ROOT}/test.onnx", "/etc/passwd"),
            ),
            id="symlink-as-model",
        ),
        pytest.param(
            lambda: _tar(_GOOD, _link(f"{_ROOT}/espeak-ng-data/out", "../../..")),
            id="symlink-in-data-tree",
        ),
        pytest.param(
            lambda: _tar(
                _GOOD,
                _link(f"{_ROOT}/espeak-ng-data/hard", "/etc/passwd", tarfile.LNKTYPE),
            ),
            id="hardlink-in-data-tree",
        ),
        pytest.param(
            lambda: _tar({k: v for k, v in _GOOD.items() if "tokens" not in k}),
            id="missing-expected-file",
        ),
        pytest.param(
            lambda: _tar({k: v for k, v in _GOOD.items() if "espeak" not in k}),
            id="missing-data-tree",
        ),
        pytest.param(
            lambda: _tar({k: v for k, v in _GOOD.items() if "phontab" not in k}),
            id="missing-data-marker",
        ),
    ],
)
def test_a_malicious_or_incomplete_archive_is_rejected(
    tmp_path: Path, server: _Server, build: Callable[[], bytes]
) -> None:
    store = _store(tmp_path, _entry(server, build()))

    assert _install_error(store).code is _CODE.INVALID_SNAPSHOT

    assert not store.is_installed("test-voice")
    assert not (tmp_path / "evil").exists()
    assert not (tmp_path / "data/models/evil").exists()
    assert not (tmp_path / "data/models/tts/test-voice").exists()
    # A verified but unusable archive is final: nothing is kept to retry on.
    assert not (tmp_path / "data/models/tts/test-voice.installing").exists()


def test_members_outside_the_archive_root_and_unwanted_links_are_ignored(
    tmp_path: Path, server: _Server
) -> None:
    data = _tar(
        {**_GOOD, "other-root/file": b"x"},
        _link(f"{_ROOT}/dict/link", "/etc/passwd"),  # not extracted, so harmless
    )
    store = _store(tmp_path, _entry(server, data))

    store.install("test-voice")

    directory = tmp_path / "data/models/tts/test-voice"
    assert store.is_installed("test-voice")
    assert not (directory / "dict").exists()
    assert not (directory / "other-root").exists()


def test_cancelling_keeps_the_partial_and_the_next_install_resumes(
    tmp_path: Path, server: _Server
) -> None:
    entry = _entry(server, _tar(_GOOD))
    store = _store(tmp_path, entry)
    staging = tmp_path / "data/models/tts/test-voice.installing"

    error = _install_error(store, cancelled=lambda: True)

    assert error.code is _CODE.CANCELLED
    assert not store.is_installed("test-voice")
    assert not (tmp_path / "data/models/tts/test-voice").exists()
    assert staging.is_dir()
    (partial,) = staging.glob("*.part")
    partial.write_bytes(server.routes["/m.tar.bz2"][:50])  # a cut download
    server.requests.clear()

    store.install("test-voice")

    assert store.is_installed("test-voice")
    assert server.requests == ["bytes=50-"]
    assert not staging.exists()


def test_cancelling_during_extraction_publishes_nothing(
    tmp_path: Path, server: _Server
) -> None:
    store = _store(tmp_path, _entry(server, _tar(_GOOD)))
    polls: list[None] = []

    def cancelled() -> bool:
        polls.append(None)
        # Let the verification pass read the archive, then stop on the first member.
        return len(polls) > 2

    error = _install_error(store, cancelled=cancelled)

    assert error.code is _CODE.CANCELLED
    assert not (tmp_path / "data/models/tts/test-voice").exists()
    assert not store.is_installed("test-voice")


def test_remove_deletes_the_whole_directory_and_partials(
    tmp_path: Path, server: _Server
) -> None:
    store = _store(tmp_path, _entry(server, _tar(_GOOD)))
    store.install("test-voice")
    leftover = tmp_path / "data/models/tts/test-voice.installing"
    leftover.mkdir()
    (leftover / "x.part").write_bytes(b"123")
    used = store.disk_usage("test-voice") or 0

    freed = store.remove("test-voice")

    assert freed == used + 3
    assert not store.is_installed("test-voice")
    assert store.disk_usage("test-voice") is None
    assert _tree(tmp_path / "data/models/tts") == set()
    assert store.remove("test-voice") == 0
    assert store.remove("not-in-catalog") == 0


def test_a_tampered_install_is_not_reported_as_installed(
    tmp_path: Path, server: _Server
) -> None:
    store = _store(tmp_path, _entry(server, _tar(_GOOD)))
    store.install("test-voice")
    model = tmp_path / "data/models/tts/test-voice/test.onnx"

    model.write_bytes(b"short")
    assert not store.is_installed("test-voice")
    assert store.manifest("test-voice") is None
    model.unlink()
    assert not store.is_installed("test-voice")

    # Re-installing replaces the damaged copy.
    store.install("test-voice")
    assert store.is_installed("test-voice")


def test_an_unknown_model_cannot_be_installed(tmp_path: Path, server: _Server) -> None:
    store = _store(tmp_path, _entry(server, _tar(_GOOD)))

    with pytest.raises(ModelInstallationError) as caught:
        store.install("../../etc")

    assert caught.value.code is _CODE.INVALID_SNAPSHOT
    assert not store.is_installed("../../etc")


def _onnx_with_metadata(props: dict[str, str]) -> bytes:
    """A minimal ModelProto: only ``metadata_props`` (field 14)."""
    out = b""
    for key, value in props.items():
        k, v = key.encode(), value.encode()
        entry = b"\x0a" + bytes([len(k)]) + k + b"\x12" + bytes([len(v)]) + v
        out += b"\x72" + bytes([len(entry)]) + entry
    return out


def test_the_manifest_reads_the_real_voices_from_the_onnx_metadata(
    tmp_path: Path, server: _Server
) -> None:
    onnx = _onnx_with_metadata({"n_speakers": "2", "speaker_names": "ana,luis"})
    members = {**_GOOD, f"{_ROOT}/test.onnx": onnx}
    store = _store(tmp_path, _entry(server, _tar(members)))

    manifest = store.install("test-voice")

    assert [(v.id, v.name) for v in manifest.voices] == [("0", "ana"), ("1", "luis")]
    assert manifest.voices[0].languages == ("es",)


def test_the_manifest_uses_the_curated_name_when_the_onnx_names_no_speaker(
    tmp_path: Path, server: _Server
) -> None:
    onnx = _onnx_with_metadata({"n_speakers": "1"})  # like the real Piper es_MX
    members = {**_GOOD, f"{_ROOT}/test.onnx": onnx}
    store = _store(tmp_path, _entry(server, _tar(members)))

    manifest = store.install("test-voice")

    assert [(v.id, v.name, v.languages) for v in manifest.voices] == [
        ("0", "Test", ("es",))
    ]
