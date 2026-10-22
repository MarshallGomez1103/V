"""A restart removes the temporaries a killed process left; real files stay."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from voz.application.get_transcription_options import GetTranscriptionOptions
from voz.application.ports.transcription_options import (
    ModelRegistration,
    RuntimeAvailability,
)
from voz.bootstrap import create_app
from voz.infrastructure.paths import VozPaths


class _Offline:
    def list_models(self) -> tuple[ModelRegistration, ...]:
        return ()

    def probe(self, provider_id: str) -> RuntimeAvailability:
        return RuntimeAvailability(False)


def _app(paths: VozPaths) -> TestClient:
    return TestClient(
        create_app(
            paths=paths,
            transcription_options=GetTranscriptionOptions(_Offline(), _Offline()),
        )
    )


def test_restart_discards_interrupted_temporaries_and_keeps_real_files(
    tmp_path: Path, platform_mode: str
) -> None:
    for name in ("data", "state"):
        (tmp_path / name).mkdir()
    paths = VozPaths(
        tmp_path / "config", tmp_path / "data", tmp_path / "cache", tmp_path / "state"
    )
    project = paths.data / "projects" / str(uuid4())
    originals = project / "originals"
    derivatives = project / "derivatives"
    originals.mkdir(parents=True)
    derivatives.mkdir()
    original = originals / f"{uuid4()}.wav"
    original.write_bytes(b"original")
    derivative = derivatives / f"{uuid4()}.inference.wav"
    derivative.write_bytes(b"derivative")
    orphans = [
        originals / f".import-{uuid4()}.tmp",
        derivatives / f".normalize-{uuid4()}.tmp.wav",
    ]
    for orphan in orphans:
        orphan.write_bytes(b"partial")
    # Killed between publishing and unlinking: the temporary is a second name
    # for the finished derivative.
    linked = derivatives / f".normalize-{uuid4()}.tmp.wav"
    os.link(derivative, linked)
    orphans.append(linked)
    # Synthesis: a job killed mid-render leaves only its temporary; a finished
    # one keeps its audio, and an unrelated file in the directory is not ours.
    synthesis = paths.data / "synthesis"
    killed, finished, mixed = (synthesis / str(uuid4()) for _ in range(3))
    for directory in (killed, finished, mixed):
        directory.mkdir(parents=True)
    audio = finished / "audio.wav"
    audio.write_bytes(b"audio")
    stray = mixed / "notes.txt"
    stray.write_bytes(b"keep")
    for directory in (killed, finished, mixed):
        orphans.append(directory / f".audio-{uuid4()}.tmp")
        orphans[-1].write_bytes(b"partial")

    del platform_mode  # native and Windows-style filesystem layers
    with _app(paths):
        pass

    assert [orphan for orphan in orphans if orphan.exists()] == []
    assert original.read_bytes() == b"original"
    assert derivative.read_bytes() == b"derivative"
    assert not killed.exists()  # nothing left in it: the directory goes too
    assert audio.read_bytes() == b"audio"
    assert stray.read_bytes() == b"keep"
