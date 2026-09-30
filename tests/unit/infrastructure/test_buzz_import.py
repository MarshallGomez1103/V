"""Importing a Buzz snapshot never mutates the original tree."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_buzz_cache import (
    PAYLOADS,
    REVISION,
    SOURCE,
    build_snapshot,
    make_entry,
)

from voz.application.import_external_model import ImportExternalModel
from voz.application.ports.external_models import (
    ExternalModelCandidate,
    ExternalModelError,
    ExternalModelFailureCode,
)
from voz.application.ports.model_installation import (
    ModelFile,
    ModelInstallation,
    ModelInstallationError,
)
from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.infrastructure.buzz_cache import BuzzModelCache
from voz.infrastructure.model_storage import FileSystemModelStore


class FakeSource:
    def __init__(self, *candidates: ExternalModelCandidate) -> None:
        self._candidates = candidates

    def find_candidates(self) -> tuple[ExternalModelCandidate, ...]:
        return self._candidates


class FakeStore:
    def __init__(self) -> None:
        self.calls: list[tuple[ModelDescriptor, tuple[str, ...], Path]] = []

    def import_local_snapshot(
        self,
        descriptor: ModelDescriptor,
        files: Sequence[ModelFile],
        snapshot_dir: Path,
        *,
        progress: object = None,
        cancelled: object = None,
    ) -> ModelInstallation:
        names = tuple(item.name for item in files)
        self.calls.append((descriptor, names, snapshot_dir))
        return ModelInstallation(descriptor, datetime.now(UTC))


def candidate(origin: str = "buzz", revision: str = REVISION) -> ExternalModelCandidate:
    return ExternalModelCandidate(origin, SOURCE, revision, Path("/snap"), 1)


def test_execute_imports_the_matching_candidate() -> None:
    store = FakeStore()
    use_case = ImportExternalModel(FakeSource(candidate()), store, (make_entry(),))

    installation = use_case.execute("tiny")

    assert installation.descriptor == make_entry().descriptor
    assert store.calls == [
        (make_entry().descriptor, tuple(PAYLOADS), Path("/snap")),
    ]


def test_unknown_model_id() -> None:
    use_case = ImportExternalModel(
        FakeSource(candidate()), FakeStore(), (make_entry(),)
    )

    with pytest.raises(ExternalModelError) as raised:
        use_case.execute("nope")

    assert raised.value.code is ExternalModelFailureCode.UNKNOWN_MODEL


@pytest.mark.parametrize(
    "found",
    [(), (candidate(origin="other"),), (candidate(revision="f" * 40),)],
)
def test_not_found_when_no_exact_candidate(
    found: tuple[ExternalModelCandidate, ...],
) -> None:
    store = FakeStore()
    use_case = ImportExternalModel(FakeSource(*found), store, (make_entry(),))

    with pytest.raises(ExternalModelError) as raised:
        use_case.execute("tiny")

    assert raised.value.code.value == "external_model_not_found"
    assert store.calls == []


def test_available_lists_only_catalog_matches() -> None:
    use_case = ImportExternalModel(
        FakeSource(candidate()), FakeStore(), (make_entry(),)
    )

    assert use_case.available() == ((make_entry().descriptor, candidate()),)
    assert use_case.available("other") == ()


def _fingerprint(root: Path) -> dict[str, tuple[object, ...]]:
    """Hash + mtime (+ mode, inode, size, link target) of every node, incl. dirs."""
    state: dict[str, tuple[object, ...]] = {}
    for base, dirs, files in os.walk(root):
        for name in [*dirs, *files]:
            path = Path(base, name)
            info = path.lstat()
            if path.is_symlink():
                detail: object = os.readlink(path)
            elif path.is_file():
                detail = hashlib.sha256(path.read_bytes()).hexdigest()
            else:
                detail = None
            state[str(path.relative_to(root))] = (
                info.st_mtime_ns,
                info.st_mode,
                info.st_size,
                info.st_ino,
                detail,
            )
    return state


def test_detect_and_import_leave_the_buzz_tree_byte_identical(
    tmp_path: Path,
) -> None:
    buzz = tmp_path / "buzz-models"
    build_snapshot(buzz)
    before = _fingerprint(buzz)
    store = FileSystemModelStore(
        data_root=tmp_path / "data", cache_root=tmp_path / "cache"
    )
    entry = make_entry()
    calls: list[tuple[int, int]] = []

    installation = ImportExternalModel(
        BuzzModelCache([buzz], lambda: (entry,)), store, (entry,)
    ).execute("tiny", progress=lambda done, total: calls.append((done, total)))

    assert store.is_installed(entry.descriptor)
    assert installation.descriptor == entry.descriptor
    assert calls and calls[-1][0] == calls[-1][1]
    assert _fingerprint(buzz) == before


def test_store_failure_propagates_and_original_is_untouched(tmp_path: Path) -> None:
    buzz = tmp_path / "buzz-models"
    # Same size as the catalog but wrong bytes: only the store's hash check sees it.
    snapshot = build_snapshot(buzz)
    blob = (snapshot / "model.bin").resolve()
    blob.write_bytes(b"x" * len(PAYLOADS["model.bin"]))
    entry = make_entry()
    before = _fingerprint(buzz)
    store = FileSystemModelStore(
        data_root=tmp_path / "data", cache_root=tmp_path / "cache"
    )

    with pytest.raises(ModelInstallationError):
        ImportExternalModel(
            BuzzModelCache([buzz], lambda: (entry,)), store, (entry,)
        ).execute("tiny")

    assert not store.is_installed(entry.descriptor)
    assert _fingerprint(buzz) == before


def test_cancellation_propagates_and_original_is_untouched(tmp_path: Path) -> None:
    buzz = tmp_path / "buzz-models"
    build_snapshot(buzz)
    before = _fingerprint(buzz)
    entry = make_entry()
    store = FileSystemModelStore(
        data_root=tmp_path / "data", cache_root=tmp_path / "cache"
    )

    with pytest.raises(ModelInstallationError) as raised:
        ImportExternalModel(
            BuzzModelCache([buzz], lambda: (entry,)), store, (entry,)
        ).execute("tiny", cancelled=lambda: True)

    assert "cancel" in raised.value.code.value
    assert not store.is_installed(entry.descriptor)
    assert _fingerprint(buzz) == before
