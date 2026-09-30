"""Read-only Buzz cache discovery over simulated HuggingFace hub trees."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from voz.application.ports.external_models import ExternalModelSource
from voz.application.ports.model_installation import ModelFile
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.infrastructure.asr.catalog import CatalogEntry
from voz.infrastructure.buzz_cache import BuzzModelCache, default_buzz_roots

SOURCE = "Acme/faster-whisper-tiny"
REVISION = "0123456789abcdef0123456789abcdef01234567"
PAYLOADS = {
    "model.bin": b"weights" * 100,
    "config.json": b'{"k": 1}',
    "vocabulary.txt": b"a\nb\n",
}


def make_entry(source: str = SOURCE, revision: str = REVISION) -> CatalogEntry:
    return CatalogEntry(
        descriptor=ModelDescriptor(
            provider_id="faster-whisper",
            model_id="tiny",
            display_name="Tiny",
            capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
            source=source,
            revision=revision,
        ),
        files=tuple(
            ModelFile(
                name,
                len(data),
                hashlib.sha256(data).hexdigest() if name == "model.bin" else None,
            )
            for name, data in PAYLOADS.items()
        ),
        license="MIT",
        multilingual=True,
    )


def build_snapshot(
    root: Path,
    *,
    source: str = SOURCE,
    revision: str = REVISION,
    payloads: dict[str, bytes] | None = None,
) -> Path:
    """Create ``models--org--repo/{blobs,snapshots/<rev>}`` with blob symlinks."""
    repo = root / ("models--" + source.replace("/", "--"))
    snapshot = repo / "snapshots" / revision
    (repo / "blobs").mkdir(parents=True, exist_ok=True)
    (repo / "refs").mkdir(exist_ok=True)
    (repo / "refs" / "main").write_text(revision)
    snapshot.mkdir(parents=True, exist_ok=True)
    (snapshot / ".buzz_complete").touch()
    for name, data in (PAYLOADS if payloads is None else payloads).items():
        blob = repo / "blobs" / hashlib.sha256(data).hexdigest()
        blob.write_bytes(data)
        (snapshot / name).symlink_to(os.path.join("..", "..", "blobs", blob.name))
    return snapshot


def cache(*roots: Path) -> BuzzModelCache:
    return BuzzModelCache(roots, lambda: (make_entry(),))


def test_valid_snapshot_is_a_candidate(tmp_path: Path) -> None:
    snapshot = build_snapshot(tmp_path)

    found = cache(tmp_path).find_candidates()

    assert isinstance(cache(tmp_path), ExternalModelSource)
    assert len(found) == 1
    assert found[0].origin == "buzz"
    assert (found[0].source, found[0].revision) == (SOURCE, REVISION)
    assert found[0].snapshot_dir == snapshot
    assert found[0].total_bytes == sum(len(data) for data in PAYLOADS.values())


def test_first_root_wins_and_missing_roots_are_ignored(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    build_snapshot(first)
    build_snapshot(second)

    found = cache(tmp_path / "nope", first, second).find_candidates()

    assert [item.snapshot_dir for item in found] == [
        first / f"models--Acme--faster-whisper-tiny/snapshots/{REVISION}"
    ]


def test_wrong_size_is_rejected(tmp_path: Path) -> None:
    build_snapshot(tmp_path, payloads={**PAYLOADS, "model.bin": b"truncated"})

    assert cache(tmp_path).find_candidates() == ()


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    build_snapshot(tmp_path, payloads={"model.bin": PAYLOADS["model.bin"]})

    assert cache(tmp_path).find_candidates() == ()


def test_dangling_symlink_is_rejected(tmp_path: Path) -> None:
    snapshot = build_snapshot(tmp_path)
    next((snapshot.parents[1] / "blobs").iterdir()).unlink()

    assert cache(tmp_path).find_candidates() == ()


def test_different_revision_is_rejected(tmp_path: Path) -> None:
    build_snapshot(tmp_path, revision="f" * 40)

    assert cache(tmp_path).find_candidates() == ()


def test_different_repository_is_rejected(tmp_path: Path) -> None:
    build_snapshot(tmp_path, source="Other/faster-whisper-tiny")

    assert cache(tmp_path).find_candidates() == ()


def test_symlink_escaping_the_repo_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "models"
    snapshot = build_snapshot(root)
    outside = tmp_path / "secret.bin"
    outside.write_bytes(PAYLOADS["model.bin"])  # right size, wrong place
    (snapshot / "model.bin").unlink()
    (snapshot / "model.bin").symlink_to(outside)

    assert cache(root).find_candidates() == ()


def test_symlink_into_a_sibling_repo_is_rejected(tmp_path: Path) -> None:
    snapshot = build_snapshot(tmp_path)
    other = build_snapshot(tmp_path, source="Other/repo", payloads={"x": b"x" * 800})
    stolen = next((other.parents[1] / "blobs").iterdir())
    stolen.write_bytes(PAYLOADS["model.bin"])
    (snapshot / "model.bin").unlink()
    (snapshot / "model.bin").symlink_to(stolen)

    assert cache(tmp_path).find_candidates() == ()


def test_repo_directory_symlinked_out_of_the_root_is_rejected(
    tmp_path: Path,
) -> None:
    elsewhere = tmp_path / "elsewhere"
    build_snapshot(elsewhere)
    root = tmp_path / "models"
    root.mkdir()
    (root / "models--Acme--faster-whisper-tiny").symlink_to(
        elsewhere / "models--Acme--faster-whisper-tiny"
    )

    assert cache(root).find_candidates() == ()


def test_directory_in_place_of_a_file_is_rejected(tmp_path: Path) -> None:
    snapshot = build_snapshot(tmp_path)
    (snapshot / "config.json").unlink()
    (snapshot / "config.json").mkdir()

    assert cache(tmp_path).find_candidates() == ()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")
def test_unreadable_root_is_ignored_without_raising(tmp_path: Path) -> None:
    locked, good = tmp_path / "locked", tmp_path / "good"
    build_snapshot(locked)
    build_snapshot(good)
    locked.chmod(0)
    try:
        found = cache(locked, good).find_candidates()
    finally:
        locked.chmod(0o755)

    assert [item.snapshot_dir.parents[2] for item in found] == [good]


def test_openai_whisper_pt_files_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "whisper").mkdir()
    (tmp_path / "whisper" / "tiny.pt").write_bytes(PAYLOADS["model.bin"])

    assert cache(tmp_path).find_candidates() == ()


def test_unpinned_catalog_entries_are_skipped(tmp_path: Path) -> None:
    build_snapshot(tmp_path)
    entry = make_entry()
    unpinned = CatalogEntry(
        ModelDescriptor("faster-whisper", "x", "X", frozenset({ModelCapability.CPU})),
        entry.files,
        "MIT",
        True,
    )

    assert BuzzModelCache([tmp_path], lambda: (unpinned,)).find_candidates() == ()


def test_default_roots_order_and_dedup(tmp_path: Path) -> None:
    home = tmp_path / "home"
    flatpak = home / ".var/app/io.github.chidiwilliams.Buzz/cache/Buzz/models"

    assert default_buzz_roots({}, home) == (flatpak, home / ".cache/Buzz/models")
    assert default_buzz_roots(
        {"BUZZ_MODEL_ROOT": "/x", "XDG_CACHE_HOME": "/xdg"}, home
    ) == (Path("/x"), flatpak, Path("/xdg/Buzz/models"))


def test_empty_buzz_model_root_disables_detection(tmp_path: Path) -> None:
    assert default_buzz_roots({"BUZZ_MODEL_ROOT": ""}, tmp_path) == ()
    assert default_buzz_roots({"BUZZ_MODEL_ROOT": "  "}, tmp_path) == ()


def test_default_catalog_is_the_real_one(tmp_path: Path) -> None:
    # Nothing on disk: just proves the default wiring imports and runs.
    assert BuzzModelCache([tmp_path]).find_candidates() == ()
