"""Resumable, size- and SHA-256-pinned download of one release artifact.

Shared by the stores that install a pinned upstream file (diarization models,
speech synthesis archives). The caller owns a staging directory: a verified file
ends there as ``artifact.name``; an interrupted download resumes from its
``.part`` file. Stdlib only; nothing here executes or extracts what it fetches.
"""

from __future__ import annotations

import hashlib
import http.client
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from voz.application.ports.model_installation import (
    CancelCheck,
    ModelInstallationError,
    ModelInstallationFailureCode,
)

_Code = ModelInstallationFailureCode
_BLOCK_BYTES = 1024 * 1024


class PinnedArtifact(Protocol):
    """What the fetcher needs to know about an upstream file."""

    @property
    def name(self) -> str: ...
    @property
    def url(self) -> str: ...
    @property
    def size_bytes(self) -> int: ...
    @property
    def sha256(self) -> str: ...


class ArtifactFetcher:
    """Download into ``staging`` and verify; ``label`` names it in messages."""

    def __init__(self, staging: Path, *, label: str, timeout_seconds: float) -> None:
        self._staging = staging
        self._label = label
        self._timeout = timeout_seconds

    def fetch(
        self,
        artifact: PinnedArtifact,
        on_bytes: Callable[[int], None],
        cancelled: CancelCheck | None,
    ) -> Path:
        """Leave a verified ``artifact.name`` in staging, resuming a ``.part``."""
        finished = self._staging / artifact.name
        partial = self._staging / f"{artifact.name}.part"
        if finished.is_file() and self._matches(finished, artifact, cancelled):
            on_bytes(artifact.size_bytes)
            return finished
        finished.unlink(missing_ok=True)
        self._download_part(artifact, partial, on_bytes, cancelled)
        if not self._matches(partial, artifact, cancelled):
            partial.unlink(missing_ok=True)
            raise self._mismatch()
        os.replace(partial, finished)
        return finished

    def _download_part(
        self,
        artifact: PinnedArtifact,
        partial: Path,
        on_bytes: Callable[[int], None],
        cancelled: CancelCheck | None,
    ) -> None:
        for _attempt in range(2):
            try:
                offset = partial.stat().st_size
            except FileNotFoundError:
                offset = 0
            if offset > artifact.size_bytes:
                partial.unlink()
                offset = 0
            if offset == artifact.size_bytes:
                on_bytes(offset)
                return
            headers = {"Accept-Encoding": "identity", "User-Agent": "voz-model-store"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            try:
                response = urllib.request.urlopen(
                    urllib.request.Request(artifact.url, headers=headers),
                    timeout=self._timeout,
                )
            except urllib.error.HTTPError as error:
                error.close()
                if error.code == 416 and offset:  # stale partial: start over once
                    partial.unlink(missing_ok=True)
                    continue
                raise ModelInstallationError(
                    _Code.HTTP_ERROR,
                    "The model server rejected the request.",
                    status=error.code,
                ) from error
            except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
                raise self._network_failure() from error
            with response:
                status = int(response.status)
                resumed = False
                if offset and status == 206:
                    if not str(response.headers.get("Content-Range", "")).startswith(
                        f"bytes {offset}-"
                    ):
                        partial.unlink(missing_ok=True)
                        continue
                    resumed = True
                elif status != 200:
                    raise ModelInstallationError(
                        _Code.HTTP_ERROR,
                        "The model server rejected the request.",
                        status=status,
                    )
                written = offset if resumed else 0
                with partial.open("ab" if resumed else "wb") as output:
                    on_bytes(written)
                    while block := self._read(response):
                        if cancelled is not None and cancelled():
                            raise self._cancelled()
                        written += len(block)
                        if written > artifact.size_bytes:
                            break
                        output.write(block)
                        on_bytes(written)
                    output.flush()
                    os.fsync(output.fileno())
                if written == artifact.size_bytes and not response.length:
                    return
                # Too long, or a cut connection that read() reported as clean EOF.
                if written > artifact.size_bytes:
                    partial.unlink(missing_ok=True)
                    raise self._mismatch()
                raise self._network_failure()
        raise ModelInstallationError(
            _Code.DOWNLOAD_FAILED, "The model file could not be downloaded."
        )

    def _read(self, response: http.client.HTTPResponse) -> bytes:
        try:
            return response.read(_BLOCK_BYTES)
        except (OSError, http.client.HTTPException) as error:
            raise self._network_failure() from error

    def _mismatch(self) -> ModelInstallationError:
        return ModelInstallationError(
            _Code.CHECKSUM_MISMATCH,
            f"The downloaded {self._label} failed verification.",
        )

    @staticmethod
    def _network_failure() -> ModelInstallationError:
        return ModelInstallationError(
            _Code.NETWORK_ERROR, "The model server could not be reached in time."
        )

    @staticmethod
    def _cancelled() -> ModelInstallationError:
        return ModelInstallationError(
            _Code.CANCELLED, "The installation was cancelled."
        )

    def _matches(
        self,
        path: Path,
        artifact: PinnedArtifact,
        cancelled: CancelCheck | None,
    ) -> bool:
        if path.stat().st_size != artifact.size_bytes:
            return False
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while block := source.read(_BLOCK_BYTES):
                if cancelled is not None and cancelled():
                    raise self._cancelled()
                digest.update(block)
        return digest.hexdigest() == artifact.sha256


__all__ = ["ArtifactFetcher", "PinnedArtifact"]
