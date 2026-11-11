"""A file added to a project is copied into the data directory, never changed."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient

from voz.bootstrap import create_app
from voz.interfaces.api.media import FILENAME_HEADER

REPOSITORY_ROOT = Path(__file__).parents[2]
SOURCE = REPOSITORY_ROOT / "tests/fixtures/media/synthetic-tone.wav"

pytestmark = pytest.mark.skipif(
    shutil.which("ffprobe") is None,
    reason="ffprobe is required for real probe coverage",
)


@pytest.fixture
def client() -> Iterator[httpx.Client]:
    with TestClient(create_app()) as test_client:
        yield cast(httpx.Client, test_client)


def _upload_source(client: httpx.Client) -> Path:
    """Add ``SOURCE`` to a new project and return where the app stored its copy."""
    project = client.post("/api/projects", json={"name": "Course"}).json()
    response = client.post(
        f"/api/projects/{project['id']}/media",
        content=SOURCE.read_bytes(),
        headers={FILENAME_HEADER: quote(SOURCE.name)},
    )
    assert response.status_code == 201
    media_asset_id = response.json()["media_asset_id"]
    data_dir = Path(os.environ["XDG_DATA_HOME"]) / "voz"
    return (
        data_dir
        / "projects"
        / project["id"]
        / "originals"
        / f"{media_asset_id}.original"
    )


def _repo_snapshot() -> tuple[list[str], list[str]]:
    return (
        sorted(entry.name for entry in REPOSITORY_ROOT.iterdir()),
        sorted(entry.name for entry in SOURCE.parent.iterdir()),
    )


def test_uploaded_copy_lives_in_data_dir_and_source_is_untouched(
    client: httpx.Client,
) -> None:
    sha_before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    mtime_before = SOURCE.stat().st_mtime_ns
    repo_before = _repo_snapshot()

    copy = _upload_source(client)

    data_home = Path(os.environ["XDG_DATA_HOME"]).resolve()
    assert copy.is_file()
    assert copy.resolve().is_relative_to(data_home)
    assert not copy.resolve().is_relative_to(REPOSITORY_ROOT.resolve())
    assert hashlib.sha256(copy.read_bytes()).hexdigest() == sha_before
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == sha_before
    assert SOURCE.stat().st_mtime_ns == mtime_before
    assert _repo_snapshot() == repo_before


def test_original_copy_is_read_only(client: httpx.Client) -> None:
    copy = _upload_source(client)

    assert stat.S_IMODE(copy.stat().st_mode) & 0o222 == 0
