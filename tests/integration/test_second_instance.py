"""A second server on the same data neither sweeps nor recovers what the first runs."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from voz import bootstrap
from voz.application.get_transcription_options import GetTranscriptionOptions
from voz.application.ports.transcription_options import (
    ModelRegistration,
    RuntimeAvailability,
)
from voz.bootstrap import create_app
from voz.infrastructure.instance_lock import InstanceLockError
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


def _paths(tmp_path: Path) -> VozPaths:
    return VozPaths(
        tmp_path / "config", tmp_path / "data", tmp_path / "cache", tmp_path / "state"
    )


def test_second_server_is_refused_before_it_touches_the_first_ones_files(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    originals = paths.data / "projects" / str(uuid4()) / "originals"
    originals.mkdir(parents=True)
    live_import = originals / f".import-{uuid4()}.tmp"

    with _app(paths):
        live_import.write_bytes(b"upload in flight")  # the first server is serving
        with pytest.raises(InstanceLockError) as refused, _app(paths):
            pass

        assert refused.value.code == "instance_already_running"
        assert live_import.read_bytes() == b"upload in flight"

    with _app(paths):  # the lock goes with the first server
        pass


def test_a_startup_that_fails_after_taking_the_lock_gives_it_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)

    def broken_migration(*_arguments: object) -> None:
        raise RuntimeError("migration failed")

    with monkeypatch.context() as patch:
        patch.setattr(bootstrap, "upgrade_to_head", broken_migration)
        with pytest.raises(RuntimeError, match="migration failed"), _app(paths):
            pass

    with _app(paths):  # a retry is not told another server is running
        pass
