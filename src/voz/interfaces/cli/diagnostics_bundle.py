"""Redacted support bundle behind ``voz doctor --bundle``.

The bundle holds only aggregate, non-identifying facts: the redacted doctor
report, package versions, the schema revision, and job/project counts. It never
reads project names, file names, transcript text, media, models, the database
itself, or environment variable values.
"""

from __future__ import annotations

import dataclasses
import importlib.metadata
import json
import platform
import re
import sqlite3
import sys
import zipfile
from contextlib import closing
from pathlib import Path
from typing import cast

from voz.bootstrap import DATABASE_FILENAME
from voz.infrastructure.paths import VozPaths
from voz.infrastructure.persistence.migrate import head_revision
from voz.interfaces.cli.doctor import DoctorReport

PACKAGES = (
    "voz-transcriber",
    "fastapi",
    "sqlalchemy",
    "alembic",
    "faster-whisper",
    "ctranslate2",
)
_SAFE_ERROR_CODE = re.compile(r"[A-Za-z0-9_.-]{1,64}")

README = """\
Paquete de diagnóstico de VOZ (generado por `voz doctor --bundle`).

Contiene, y nada más:
- doctor.json: el resultado de `voz doctor` con rutas redactadas.
- versions.json: versiones de VOZ, Python, la plataforma y paquetes clave.
- database.json: revisión de esquema Alembic, número de proyectos, número de
  trabajos por estado y códigos de error de los trabajos fallidos.
- README.txt: este archivo.

Redacción: la carpeta personal se reemplaza por `~` y las carpetas XDG por
`$XDG_CONFIG_HOME`, `$XDG_DATA_HOME`, `$XDG_CACHE_HOME` y `$XDG_STATE_HOME`.

Nunca incluye: la base de datos, audio o video, transcripciones, nombres de
proyectos o de archivos, modelos, ni valores de variables de entorno (de las
claves API opcionales solo se informa `set` o `unset`).

Revísalo antes de compartirlo: es un zip normal y puedes abrirlo.
"""


def _replacements(paths: VozPaths, home: Path) -> list[tuple[str, str]]:
    pairs = [
        (str(paths.config.parent), "$XDG_CONFIG_HOME"),
        (str(paths.data.parent), "$XDG_DATA_HOME"),
        (str(paths.cache.parent), "$XDG_CACHE_HOME"),
        (str(paths.state.parent), "$XDG_STATE_HOME"),
        (str(home), "~"),
    ]
    return sorted((pair for pair in pairs if pair[0]), key=lambda p: -len(p[0]))


def redact(value: object, paths: VozPaths, home: Path) -> object:
    """Replace home/XDG locations in every string of a JSON-like structure."""
    pairs = _replacements(paths, home)

    def walk(node: object) -> object:
        if isinstance(node, str):
            for old, new in pairs:
                node = node.replace(old, new)
            return node
        if isinstance(node, dict):
            items = cast(dict[str, object], node).items()
            return {key: walk(item) for key, item in items}
        if isinstance(node, (list, tuple)):
            return [walk(item) for item in cast(list[object], node)]
        return node

    return walk(value)


def _versions() -> dict[str, object]:
    installed: dict[str, str | None] = {}
    for package in PACKAGES:
        try:
            installed[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            installed[package] = None
    return {
        "python": platform.python_version(),
        "implementation": sys.implementation.name,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": installed,
    }


def _database_summary(database: Path) -> dict[str, object]:
    summary: dict[str, object] = {
        "present": database.is_file(),
        "head_revision": head_revision(),
    }
    if not database.is_file():
        return summary
    try:
        # Read-only URI: diagnosing must never create or alter the database.
        with closing(sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)) as db:
            row = db.execute("SELECT version_num FROM alembic_version").fetchone()
            summary["revision"] = row[0] if row else None
            summary["projects"] = db.execute(
                "SELECT COUNT(*) FROM projects"
            ).fetchone()[0]
            summary["jobs_by_state"] = dict(
                db.execute(
                    "SELECT state, COUNT(*) FROM transcription_jobs GROUP BY state"
                ).fetchall()
            )
            failed: dict[str, int] = {}
            for code, count in db.execute(
                "SELECT error_code, COUNT(*) FROM transcription_jobs"
                " WHERE state = 'FAILED' GROUP BY error_code"
            ):
                # Only stable code-shaped values; anything else could be free text.
                key = code if code and _SAFE_ERROR_CODE.fullmatch(code) else "other"
                failed[key] = failed.get(key, 0) + count
            summary["failed_error_codes"] = failed
    except (sqlite3.Error, OSError) as error:
        summary["error"] = type(error).__name__
    return summary


def build_bundle(
    report: DoctorReport, *, paths: VozPaths, home: Path | None = None
) -> dict[str, str]:
    """Return ``{file name: text}`` for the bundle; every value is redacted."""
    home_directory = Path.home() if home is None else home
    documents: dict[str, object] = {
        "doctor.json": dataclasses.asdict(report),
        "versions.json": _versions(),
        "database.json": _database_summary(paths.data / DATABASE_FILENAME),
    }
    files = {
        name: json.dumps(
            redact(document, paths, home_directory), ensure_ascii=False, indent=2
        )
        + "\n"
        for name, document in documents.items()
    }
    files["README.txt"] = README
    return files


def write_bundle(target: Path, files: dict[str, str]) -> None:
    """Write the zip; refuses to overwrite an existing file."""
    with (
        target.open("xb") as output,
        zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive,
    ):
        for name, text in files.items():
            archive.writestr(name, text)
