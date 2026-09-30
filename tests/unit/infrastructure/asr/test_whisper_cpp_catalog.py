"""Pinned whisper.cpp catalog and its fit with the verified download store."""

import hashlib
from collections.abc import Iterator
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import pytest

from voz.application.ports.model_installation import ModelFile
from voz.domain.entities.model_descriptor import ModelCapability
from voz.infrastructure.asr.whisper_cpp_catalog import (
    PROVIDER_ID,
    REVISION,
    SOURCE,
    WhisperCppModelCatalog,
    model_filename,
    whisper_cpp_catalog,
)
from voz.infrastructure.model_storage import FileSystemModelStore


def test_catalog_pins_the_six_quantized_models() -> None:
    entries = whisper_cpp_catalog()

    assert [(e.files[0].name, e.files[0].size_bytes) for e in entries] == [
        ("ggml-large-v3-turbo-q5_0.bin", 574041195),
        ("ggml-large-v3-turbo-q8_0.bin", 874188075),
        ("ggml-large-v3-turbo.bin", 1624555275),
        ("ggml-small-q5_1.bin", 190085487),
        ("ggml-small.bin", 487601967),
        ("ggml-base.bin", 147951465),
    ]
    assert entries[0].files[0].sha256 == (
        "394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2"
    )
    assert WhisperCppModelCatalog().entries() == entries


def test_descriptors_are_pinned_local_and_consistent() -> None:
    for entry in whisper_cpp_catalog():
        descriptor = entry.descriptor
        assert descriptor.provider_id == PROVIDER_ID == "whisper-cpp"
        assert descriptor.provenance == (SOURCE, REVISION)
        assert REVISION == "5359861c739e955e79d9a303bcbc70fb988958b1"
        assert descriptor.supports(ModelCapability.TRANSCRIPTION)
        assert len(entry.files) == 1 and entry.files[0].sha256 is not None
        assert entry.files[0].name == model_filename(descriptor)
        assert entry.license == "MIT" and entry.multilingual
    ids = [entry.descriptor.model_id for entry in whisper_cpp_catalog()]
    assert len(set(ids)) == len(ids)


def test_model_filename_rejects_unsafe_ids() -> None:
    entry = whisper_cpp_catalog()[0]
    with pytest.raises(ValueError, match="safe"):
        model_filename(replace(entry.descriptor, model_id="../x"))


@pytest.fixture
def origin() -> Iterator[tuple[str, dict[str, bytes]]]:
    routes: dict[str, bytes] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            del format, args

        def do_GET(self) -> None:
            body = routes.get(self.path)
            if body is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", routes
    server.shutdown()
    server.server_close()
    thread.join()


def test_store_download_installs_the_single_ggml_file(
    tmp_path: Path, origin: tuple[str, dict[str, bytes]]
) -> None:
    url, routes = origin
    data = b"ggml-fixture" * 100
    descriptor = replace(whisper_cpp_catalog()[-1].descriptor, model_id="fixture")
    files = (
        ModelFile(
            model_filename(descriptor), len(data), hashlib.sha256(data).hexdigest()
        ),
    )
    routes[f"/{SOURCE}/resolve/{REVISION}/ggml-fixture.bin"] = data
    store = FileSystemModelStore(data_root=tmp_path / "data", cache_root=tmp_path / "c")

    store.download(descriptor, files, base_url=url)

    installed = store.resolve_path(descriptor) / "ggml-fixture.bin"
    assert installed.read_bytes() == data
    assert store.is_installed(descriptor)
