"""S14.11: the diagnostics bundle carries aggregates only, never private data."""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path
from typing import cast

from voz.infrastructure.paths import VozPaths, resolve_voz_paths
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.migrate import head_revision, upgrade_to_head
from voz.interfaces.cli.diagnostics_bundle import (
    build_bundle,
    redact,
    write_bundle,
)
from voz.interfaces.cli.doctor import DoctorCheck, DoctorReport

SECRETS = (
    "Entrevista Confidencial García",
    "grabacion-privada-de-ana.wav",
    "El paciente dijo que la contraseña es hunter2",
    "usuario-real",
    "Error con /home/usuario-real/Videos/secreto.mp4",
)


def _seed(paths: VozPaths) -> None:
    engine = create_sqlite_engine(paths.data / "voz.sqlite3")
    try:
        upgrade_to_head(engine, paths.state / "backups")
    finally:
        engine.dispose()
    with sqlite3.connect(paths.data / "voz.sqlite3") as db:
        db.execute(
            "INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)",
            ("p1", SECRETS[0], "2026-01-01T00:00:00+00:00"),
        )
        db.execute(
            "INSERT INTO media_assets (id, project_id, content_sha256, display_name,"
            " size_bytes, created_at) VALUES ('m1', 'p1', ?, ?, 10, '2026-01-01')",
            ("a" * 64, SECRETS[1]),
        )
        jobs = [
            ("j1", "COMPLETED", None),
            ("j2", "FAILED", "model_not_installed"),
            ("j3", "FAILED", "model_not_installed"),
            ("j4", "FAILED", SECRETS[4]),  # free text must never be echoed
            ("j5", "QUEUED", None),
        ]
        for job_id, state, code in jobs:
            db.execute(
                "INSERT INTO transcription_jobs (id, project_id, media_asset_id,"
                " state, progress, created_at, updated_at, error_code)"
                " VALUES (?, 'p1', 'm1', ?, 0.0, '2026-01-01', '2026-01-01', ?)",
                (job_id, state, code),
            )


def _bundle_files(tmp_path: Path) -> tuple[dict[str, str], Path]:
    home = tmp_path / "home" / "usuario-real"
    paths = resolve_voz_paths(environ={}, home=home, platform="linux")
    _seed(paths)
    report = DoctorReport(
        (
            DoctorCheck("rutas", "ok", f"escribibles: data={paths.data}"),
            DoctorCheck("ffmpeg", "ok", "ffmpeg version 6.1.1"),
        )
    )
    return build_bundle(report, paths=paths, home=home), home


def test_bundle_contains_no_seeded_names_paths_or_text(tmp_path: Path) -> None:
    files, home = _bundle_files(tmp_path)
    target = tmp_path / "out.zip"

    write_bundle(target, files)

    with zipfile.ZipFile(target) as archive:
        assert sorted(archive.namelist()) == [
            "README.txt",
            "database.json",
            "doctor.json",
            "versions.json",
        ]
        contents = {name: archive.read(name).decode() for name in archive.namelist()}
    for name, text in contents.items():
        for forbidden in (*SECRETS, str(tmp_path), str(home)):
            assert forbidden not in text, f"{forbidden!r} leaked into {name}"
    assert "$XDG_DATA_HOME/voz" in contents["doctor.json"].replace("\\\\", "/")


def test_bundle_reports_revision_and_counts(tmp_path: Path) -> None:
    files, _ = _bundle_files(tmp_path)

    database = json.loads(files["database.json"])

    assert database["present"] is True
    assert database["revision"] == database["head_revision"] == head_revision()
    assert database["projects"] == 1
    assert database["jobs_by_state"] == {"COMPLETED": 1, "FAILED": 3, "QUEUED": 1}
    assert database["failed_error_codes"] == {"model_not_installed": 2, "other": 1}


def test_bundle_versions_and_readme(tmp_path: Path) -> None:
    files, _ = _bundle_files(tmp_path)

    versions = json.loads(files["versions.json"])

    assert versions["python"]
    assert versions["packages"]["sqlalchemy"]
    assert versions["packages"]["voz-transcriber"] == "0.1.0"
    assert set(versions["packages"]) >= {"fastapi", "faster-whisper", "ctranslate2"}
    assert "nunca incluye" in files["README.txt"].lower()


def test_bundle_without_database_still_builds(tmp_path: Path) -> None:
    home = tmp_path / "home"
    paths = resolve_voz_paths(environ={}, home=home, platform="linux")

    files = build_bundle(DoctorReport(()), paths=paths, home=home)

    database = json.loads(files["database.json"])
    assert database["present"] is False
    assert not (paths.data / "voz.sqlite3").exists()  # diagnosing creates nothing


def test_redact_replaces_xdg_bases_before_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    paths = resolve_voz_paths(
        environ={"XDG_DATA_HOME": str(tmp_path / "elsewhere")},
        home=home,
        platform="linux",
    )

    result = redact({"a": [str(paths.data / "x"), str(home / "y"), 3]}, paths, home)

    assert isinstance(result, dict)
    items = cast(list[object], cast(dict[str, object], result)["a"])
    labels = [i.replace("\\", "/") if isinstance(i, str) else i for i in items]
    assert labels == ["$XDG_DATA_HOME/voz/x", "~/y", 3]
