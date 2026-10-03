"""Make ``ffmpeg`` and ``ffprobe`` available without asking the user to install them.

Windows and macOS users rarely have FFmpeg on ``PATH``. When either tool is
missing VOZ downloads one pinned static build, once, into its own cache folder,
verifies its SHA-256 and prepends that folder to ``PATH`` for this process (and
the child processes it starts). A system FFmpeg is always preferred.

Why not the ``static-ffmpeg`` package: it drags in ``twine``/``requests``/
``keyring`` (about 25 packages), downloads from a mutable ``main`` branch without
any checksum and unpacks into ``site-packages``. This module uses the same
binaries (zackees/ffmpeg_bins) but pinned to a commit and a digest, with only the
standard library.

Opt out with ``VOZ_FFMPEG_AUTO_DOWNLOAD=0`` (offline machines, tests).
"""

from __future__ import annotations

import hashlib
import http.client
import os
import platform
import shutil
import sys
import urllib.request
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal
from uuid import uuid4

_COMMIT = "df95abcb0ce6efff710dda5ef28a2f6f1dc21493"
_BASE_URL = f"https://github.com/zackees/ffmpeg_bins/raw/{_COMMIT}/v8.0"
_TIMEOUT_SECONDS = 60
_CHUNK_BYTES = 1024 * 1024
_OPT_OUT_VALUES = frozenset({"0", "false", "no", "off"})

Status = Literal["system", "cached", "downloaded", "missing", "unsupported", "failed"]


@dataclass(frozen=True, slots=True)
class _Bundle:
    sha256: str
    megabytes: int


# Digests of the zips at _COMMIT; each holds ``<key>/ffmpeg[.exe]`` and ``ffprobe``.
_BUNDLES: dict[str, _Bundle] = {
    "win32": _Bundle(
        "92662c2241e93fe71b3f3a01e94a0b0dc8cfad726019f96b83bc109ce44c5d0b", 72
    ),
    "darwin_arm64": _Bundle(
        "b2da44a8169c4d09a97db996250690c3346f72e4795521d23d3dbb1e72421207", 42
    ),
    "darwin": _Bundle(
        "70fd5b21cb37b6ea97c8b584cf76b3cc6a90179831c9c269811b9716c28605fb", 53
    ),
    "linux": _Bundle(
        "ca75b05e887c7a97676632f673031875847be83daa9794298fed9cef8cac14ad", 142
    ),
    "linux_arm64": _Bundle(
        "e03efe471c03b999f10988d5db62ae3bd94837463291b3c7755528b100e97d6f", 132
    ),
}

Announce = Callable[[str], None]
Download = Callable[[str, BinaryIO, Announce], None]


@dataclass(frozen=True, slots=True)
class FfmpegSetup:
    status: Status
    message: str
    directory: Path | None = None

    @property
    def available(self) -> bool:
        return self.status in {"system", "cached", "downloaded"}


def platform_key(system: str | None = None, machine: str | None = None) -> str | None:
    """Key of the matching bundle, or ``None`` for platforms without one."""
    system = sys.platform if system is None else system
    arm = (platform.machine() if machine is None else machine).lower() in {
        "arm64",
        "aarch64",
    }
    if system == "win32":
        return "win32"
    if system == "darwin":
        return "darwin_arm64" if arm else "darwin"
    if system.startswith("linux"):
        return "linux_arm64" if arm else "linux"
    return None


def default_cache_directory() -> Path:
    from voz.infrastructure.paths import resolve_voz_paths

    return resolve_voz_paths().cache / "ffmpeg"


def _stderr(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _download(url: str, output: BinaryIO, announce: Announce) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "voz-ffmpeg-setup"})
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
        total = int(response.headers.get("Content-Length") or 0)
        received = 0
        next_report = 10
        while chunk := response.read(_CHUNK_BYTES):
            output.write(chunk)
            received += len(chunk)
            if total and received * 100 // total >= next_report:
                announce(f"  descargado {received * 100 // total}%")
                next_report = received * 100 // total // 10 * 10 + 10


def _executables(directory: Path, key: str) -> tuple[Path, Path]:
    suffix = ".exe" if key == "win32" else ""
    return directory / f"ffmpeg{suffix}", directory / f"ffprobe{suffix}"


def _prepend_to_path(directory: Path) -> None:
    current = os.environ.get("PATH", "")
    if str(directory) not in current.split(os.pathsep):
        os.environ["PATH"] = str(directory) + os.pathsep + current


def _extract(archive: Path, key: str, destination: Path) -> None:
    """Unpack only the two known executables (no archive-controlled paths)."""
    destination.mkdir(parents=True)
    suffix = ".exe" if key == "win32" else ""
    with zipfile.ZipFile(archive) as bundle:
        for tool in ("ffmpeg", "ffprobe"):
            member = f"{key}/{tool}{suffix}"
            target = destination / f"{tool}{suffix}"
            with bundle.open(member) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o755)


def ensure_ffmpeg(
    *,
    cache_directory: Path | None = None,
    announce: Announce = _stderr,
    download: Download = _download,
    which: Callable[[str], str | None] = shutil.which,
    environ: Mapping[str, str] | None = None,
    key: str | None = None,
) -> FfmpegSetup:
    """Guarantee ``ffmpeg`` and ``ffprobe`` resolve on ``PATH``; never raises."""
    variables = os.environ if environ is None else environ
    if which("ffmpeg") and which("ffprobe"):
        return FfmpegSetup("system", "FFmpeg encontrado en el sistema.")
    if variables.get("VOZ_FFMPEG_AUTO_DOWNLOAD", "").strip().lower() in _OPT_OUT_VALUES:
        return FfmpegSetup(
            "missing", "FFmpeg no está instalado (descarga desactivada)."
        )
    selected = key or platform_key()
    bundle = _BUNDLES.get(selected) if selected else None
    if selected is None or bundle is None:
        return FfmpegSetup(
            "unsupported", "No hay FFmpeg descargable para este sistema; instálalo."
        )

    try:
        root = default_cache_directory() if cache_directory is None else cache_directory
        final = root / f"{selected}-{bundle.sha256[:12]}"
        if all(path.is_file() for path in _executables(final, selected)):
            _prepend_to_path(final)
            return FfmpegSetup("cached", "FFmpeg local de VOZ listo.", final)
        announce(
            f"VOZ necesita FFmpeg y no está instalado. Descargándolo una sola vez "
            f"(~{bundle.megabytes} MB) en {root}. Puede tardar un minuto..."
        )
        root.mkdir(parents=True, exist_ok=True)
        staging = root / f".{selected}-{uuid4().hex}.partial"
        archive = root / f".{selected}-{uuid4().hex}.zip"
        try:
            digest = hashlib.sha256()
            with archive.open("wb") as output:
                download(f"{_BASE_URL}/{selected}.zip", output, announce)
            with archive.open("rb") as written:
                while chunk := written.read(_CHUNK_BYTES):
                    digest.update(chunk)
            if digest.hexdigest() != bundle.sha256:
                raise ValueError("la suma SHA-256 de la descarga no coincide")
            _extract(archive, selected, staging)
            try:
                os.replace(staging, final)
            except OSError:
                # Another VOZ process finished first; its copy is just as good.
                if not all(path.is_file() for path in _executables(final, selected)):
                    raise
        finally:
            archive.unlink(missing_ok=True)
            shutil.rmtree(staging, ignore_errors=True)
    except (
        OSError,
        ValueError,
        KeyError,
        zipfile.BadZipFile,
        http.client.HTTPException,
    ) as error:
        return FfmpegSetup(
            "failed",
            f"No se pudo preparar FFmpeg ({type(error).__name__}: {error}). "
            "Instálalo con tu gestor de paquetes (winget install ffmpeg, "
            "brew install ffmpeg, apt install ffmpeg) o reintenta con conexión.",
        )
    _prepend_to_path(final)
    announce("FFmpeg listo.")
    return FfmpegSetup("downloaded", "FFmpeg descargado y verificado.", final)


if __name__ == "__main__":  # CI helper: print the folder holding ffmpeg/ffprobe
    result = ensure_ffmpeg()
    print(result.directory or "", end="")
    raise SystemExit(0 if result.available else 1)
