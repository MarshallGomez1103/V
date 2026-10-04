"""The directory layer on the native path and on the portable (Windows) fallback."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from voz.application.ports.media_storage import (
    MediaStorageError,
    MediaStorageErrorCode,
)
from voz.infrastructure import safe_fs
from voz.infrastructure.media_storage import FileSystemMediaStorage
from voz.infrastructure.safe_fs import (
    DirectoryDurabilityError,
    open_directory_chain,
)

pytestmark = pytest.mark.windows_ok

requires_symlinks = pytest.mark.skipif(
    os.name == "nt", reason="creating symlinks needs privileges on Windows"
)
requires_posix_modes = pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")


@pytest.fixture(params=["native", "portable"])
def mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    if request.param == "portable":
        monkeypatch.setattr(safe_fs, "FORCE_PORTABLE", True)
    return str(request.param)


def test_native_mode_uses_directory_descriptors_where_the_os_has_them() -> None:
    assert safe_fs.dir_fd_supported() is (os.name != "nt")


def test_portable_flag_disables_directory_descriptors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(safe_fs, "FORCE_PORTABLE", True)

    assert safe_fs.dir_fd_supported() is False


def test_chain_creates_opens_and_operates_inside_the_directory(
    tmp_path: Path, mode: str
) -> None:
    directory = open_directory_chain(tmp_path / "root", ("a", "b"), create=True)
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        os.close(directory.open_file("one.tmp", flags, 0o600))
        directory.link("one.tmp", "one.final")
        with pytest.raises(FileExistsError):
            directory.link("one.tmp", "one.final")  # never replaces
        assert directory.stat("one.final", follow_symlinks=False).st_nlink == 2
        directory.fsync()
        directory.unlink("one.tmp")
        directory.unlink("one.final")
        with pytest.raises(FileNotFoundError):
            directory.unlink("one.final")
    finally:
        directory.close()

    assert (tmp_path / "root" / "a" / "b").is_dir()
    assert list((tmp_path / "root" / "a" / "b").iterdir()) == []


def test_chain_without_create_reports_missing_directories(
    tmp_path: Path, mode: str
) -> None:
    (tmp_path / "root").mkdir()

    with pytest.raises(FileNotFoundError):
        open_directory_chain(tmp_path / "root", ("projects", "x"), create=False)


@requires_symlinks
def test_chain_refuses_a_symlinked_component_and_root(
    tmp_path: Path, mode: str
) -> None:
    root = tmp_path / "root"
    (root / "real").mkdir(parents=True)
    (root / "linked").symlink_to(root / "real")
    alias = tmp_path / "alias"
    alias.symlink_to(root)

    with pytest.raises(OSError):
        open_directory_chain(root, ("linked",), create=True)
    with pytest.raises(OSError, match="symbolic"):
        open_directory_chain(alias, ("real",), create=False)


@requires_symlinks
def test_open_file_refuses_symlinks_in_both_modes(tmp_path: Path, mode: str) -> None:
    root = tmp_path / "root"
    directory = open_directory_chain(root, ("d",), create=True)
    try:
        (root / "d" / "victim").write_text("secret")
        (root / "d" / "link").symlink_to(root / "d" / "victim")
        with pytest.raises(OSError):
            directory.open_file("link", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    finally:
        directory.close()


@pytest.mark.skipif(os.name == "nt", reason="NTFS directories cannot be fsynced")
def test_durability_failure_is_a_distinct_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    def broken(_descriptor: int) -> None:
        raise OSError("disk says no")

    monkeypatch.setattr(os, "fsync", broken)

    with pytest.raises(DirectoryDurabilityError):
        open_directory_chain(tmp_path / "root", ("a",), create=True, durable=True)


@requires_posix_modes
def test_unlink_removes_read_only_files_in_the_portable_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(safe_fs, "FORCE_PORTABLE", True)
    directory = open_directory_chain(tmp_path / "root", ("d",), create=True)
    target = tmp_path / "root" / "d" / "original"
    target.write_bytes(b"x")
    target.chmod(0o444)
    try:
        directory.unlink("original")
    finally:
        directory.close()

    assert not target.exists()


def test_fchmod_is_optional(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delattr(os, "fchmod", raising=False)
    descriptor = os.open(tmp_path / "f", os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        assert safe_fs.fchmod(descriptor, 0o444) is False
    finally:
        os.close(descriptor)


# -- media storage end to end on the portable layer ---------------------------


def _import(storage: FileSystemMediaStorage, source: Path) -> tuple[Path, UUID, UUID]:
    project_id, media_id = uuid4(), uuid4()
    storage.import_original(
        source=source, project_id=project_id, media_asset_id=media_id
    )
    return storage.original_path_for(project_id, media_id), project_id, media_id


@pytest.fixture
def source_file(tmp_path: Path) -> Path:
    source = tmp_path / "recording.wav"
    source.write_bytes(b"RIFF" + bytes(range(256)) * 8)
    return source


def test_portable_import_keeps_original_immutable_and_cleans_temporaries(
    tmp_path: Path, source_file: Path, mode: str
) -> None:
    before = source_file.read_bytes()
    storage = FileSystemMediaStorage(tmp_path / "data")

    stored, project_id, media_id = _import(storage, source_file)

    assert stored.read_bytes() == before
    assert source_file.read_bytes() == before
    assert not list(stored.parent.glob(".import-*"))
    if os.name != "nt":
        assert not stored.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
    with pytest.raises(MediaStorageError) as duplicate:
        storage.import_original(
            source=source_file,
            project_id=project_id,
            media_asset_id=media_id,
        )
    assert duplicate.value.code is MediaStorageErrorCode.DESTINATION_EXISTS


def test_import_marks_read_only_by_name_when_fchmod_is_missing(
    tmp_path: Path,
    source_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(safe_fs, "FORCE_PORTABLE", True)
    monkeypatch.delattr(os, "fchmod", raising=False)
    storage = FileSystemMediaStorage(tmp_path / "data")

    stored, _, _ = _import(storage, source_file)

    assert not stored.stat().st_mode & stat.S_IWUSR


@requires_symlinks
def test_portable_storage_refuses_a_symlinked_originals_directory(
    tmp_path: Path, source_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(safe_fs, "FORCE_PORTABLE", True)
    storage = FileSystemMediaStorage(tmp_path / "data")
    project_id, media_id = uuid4(), uuid4()
    projects = tmp_path / "data" / "projects" / str(project_id)
    projects.mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (projects / "originals").symlink_to(elsewhere)

    with pytest.raises(MediaStorageError) as error:
        storage.import_original(
            source=source_file, project_id=project_id, media_asset_id=media_id
        )

    assert error.value.code is MediaStorageErrorCode.UNSAFE_STORAGE_PATH
    assert list(elsewhere.iterdir()) == []


def test_remove_directory_tree_deletes_nested_read_only_files(
    tmp_path: Path, platform_mode: str
) -> None:
    root = tmp_path / "data"
    project = root / "projects" / "p1"
    (project / "originals").mkdir(parents=True)
    (project / "derivatives" / "deep").mkdir(parents=True)
    original = project / "originals" / "a.original"
    original.write_bytes(b"x")
    original.chmod(0o444)
    (project / "derivatives" / "deep" / "b.wav").write_bytes(b"y")
    keep = root / "projects" / "p2"
    keep.mkdir()
    (keep / "c").write_bytes(b"z")

    assert safe_fs.remove_directory_tree(root, ("projects", "p1")) is True

    assert not project.exists()
    assert (keep / "c").read_bytes() == b"z"


def test_remove_directory_tree_reports_a_missing_directory(
    tmp_path: Path, platform_mode: str
) -> None:
    assert safe_fs.remove_directory_tree(tmp_path, ("projects", "nope")) is False
    assert safe_fs.remove_directory_tree(tmp_path / "absent", ("x",)) is False


@requires_symlinks
def test_remove_directory_tree_never_follows_links(
    tmp_path: Path, platform_mode: str
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("keep")
    project = tmp_path / "data" / "projects" / "p1"
    project.mkdir(parents=True)
    (project / "dirlink").symlink_to(outside, target_is_directory=True)
    (project / "filelink").symlink_to(outside / "precious.txt")

    assert safe_fs.remove_directory_tree(tmp_path / "data", ("projects", "p1"))

    assert not project.exists()
    assert (outside / "precious.txt").read_text() == "keep"


@requires_symlinks
def test_remove_directory_tree_refuses_a_linked_project_directory(
    tmp_path: Path, platform_mode: str
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("keep")
    projects = tmp_path / "data" / "projects"
    projects.mkdir(parents=True)
    (projects / "p1").symlink_to(outside, target_is_directory=True)

    with pytest.raises(OSError):
        safe_fs.remove_directory_tree(tmp_path / "data", ("projects", "p1"))

    assert (outside / "precious.txt").read_text() == "keep"


def test_storage_delete_project_files_is_idempotent(
    tmp_path: Path, platform_mode: str
) -> None:
    storage = FileSystemMediaStorage(tmp_path / "data")
    project_id = uuid4()
    original = storage.original_path_for(project_id, uuid4())
    original.parent.mkdir(parents=True)
    original.write_bytes(b"x")
    original.chmod(0o444)

    storage.delete_project_files(project_id)
    storage.delete_project_files(project_id)

    assert not original.parent.parent.exists()
