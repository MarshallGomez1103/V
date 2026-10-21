"""Private, bounded raw-file staging for browser folder imports."""

from __future__ import annotations

import os
import re
import shutil
import stat
import threading
import time
from collections.abc import AsyncIterable, Callable, Generator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass, field, replace
from pathlib import Path
from uuid import uuid4

from voz.application.ports.custom_model_upload import (
    CustomModelUploadReceipt,
    CustomModelUploadRequest,
)
from voz.application.ports.custom_models import CustomModelError, CustomModelRequest
from voz.infrastructure.custom_models import allowed_file, safe_relative

_MAX_BYTES = 16 * 1024**3
_MAX_FILES = 10_000
_FAMILIES = {
    "faster-whisper": {"ctranslate2"},
    "sherpa-onnx-asr": {"whisper", "nemo_transducer"},
    "whisper-cpp": {"ggml"},
    "sherpa-onnx-tts": {"kitten", "kokoro", "vits", "matcha"},
}


def _invalid() -> CustomModelError:
    return CustomModelError(
        "custom_model_invalid", "The selected model files are not valid."
    )


def _expired() -> CustomModelError:
    return CustomModelError(
        "custom_model_upload_expired", "Select and upload the folder again."
    )


@dataclass
class _Upload:
    request: CustomModelUploadRequest = field(repr=False)
    directory: Path = field(repr=False)
    expires: float
    completed: set[int] = field(default_factory=set[int])
    pins: int = 0
    writing: bool = False
    deleted: bool = False


class FileSystemCustomModelUpload:
    def __init__(
        self,
        root: Path,
        *,
        require_space: Callable[[int], None] | None = None,
        ttl_seconds: float = 1200,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("Upload expiry must be positive.")
        self._root = root.absolute()
        self._guard = require_space
        self._ttl = ttl_seconds
        self._uploads: dict[str, _Upload] = {}
        self._lock = threading.RLock()
        self._closed = False

    def create(self, request: CustomModelUploadRequest) -> CustomModelUploadReceipt:
        names = [item.name for item in request.files]
        if (
            request.family not in _FAMILIES.get(request.engine, set())
            or not request.display_name.strip()
            or len(request.display_name) > 128
            or not request.license.strip()
            or len(request.license) > 512
            or any(ord(ch) < 32 for ch in request.display_name + request.license)
            or not 0 < len(names) <= _MAX_FILES
            or len(set(names)) != len(names)
            or len(request.file_roles) > 32
            or any(
                not safe_relative(name) or name not in names
                for name in request.file_roles.values()
            )
            or any(not allowed_file(request.engine, name) for name in names)
            or any(
                type(item.size_bytes) is not int or item.size_bytes <= 0
                for item in request.files
            )
        ):
            raise _invalid()
        # Also reject file/directory collisions and Windows case-insensitive aliases.
        folded = {name.casefold() for name in names}
        if len(folded) != len(names) or any(
            parent.as_posix().casefold() in folded
            for name in names
            for parent in Path(name).parents
            if parent != Path(".")
        ):
            raise _invalid()
        total = sum(item.size_bytes for item in request.files)
        if not 0 < total <= _MAX_BYTES:
            raise _invalid()
        with self._lock:
            if self._closed:
                raise _expired()
            self.expire()
            reserved = sum(
                sum(item.size_bytes for item in upload.request.files)
                for upload in self._uploads.values()
            )
            if len(self._uploads) >= 100 or reserved + total > _MAX_BYTES:
                raise CustomModelError(
                    "custom_model_upload_limit", "Too many pending uploads."
                )
            try:
                if self._root.is_symlink():
                    raise _invalid()
                self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
                if self._guard is not None:
                    self._guard(total)
                if shutil.disk_usage(self._root).free < reserved + total:
                    raise CustomModelError(
                        "disk_space_insufficient",
                        "Not enough free space for the upload.",
                    )
                token = uuid4().hex
                directory = self._root / token
                directory.mkdir(mode=0o700)
            except OSError:
                raise _invalid() from None
            self._uploads[token] = _Upload(
                replace(request, file_roles=dict(request.file_roles)),
                directory,
                time.monotonic() + self._ttl,
            )
            return CustomModelUploadReceipt(token, total, len(names))

    def _get(self, upload_id: str) -> _Upload:
        self.expire()
        upload = self._uploads.get(upload_id)
        if upload is None or upload.deleted:
            raise _expired()
        return upload

    async def write(
        self, upload_id: str, index: int, chunks: AsyncIterable[bytes]
    ) -> None:
        with self._lock:
            upload = self._get(upload_id)
            if (
                type(index) is not int
                or not 0 <= index < len(upload.request.files)
                or index in upload.completed
                or upload.writing
            ):
                raise _invalid()
            upload.writing = True
            upload.pins += 1
        complete = False
        try:
            item = upload.request.files[index]
            destination = upload.directory / item.name
            self._check_directory(upload.directory)
            for parent in reversed(
                destination.parent.relative_to(upload.directory).parents
            ):
                self._mkdir(upload.directory / parent)
            self._mkdir(destination.parent)
            if destination.exists() or destination.is_symlink():
                raise _invalid()
            temporary = upload.directory / (".part-" + str(index))
            flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_BINARY", 0)
            )
            count = 0
            with os.fdopen(os.open(temporary, flags, 0o600), "wb") as output:
                async for block in chunks:
                    if upload.deleted:
                        raise _expired()
                    if count + len(block) > item.size_bytes:
                        raise _invalid()
                    count += len(block)
                    output.write(block)
                if count != item.size_bytes or upload.deleted:
                    raise _invalid()
            self._check_directory(upload.directory)
            self._check_directory(destination.parent)
            if destination.exists() or destination.is_symlink():
                raise _invalid()
            os.replace(temporary, destination)
            with self._lock:
                upload.completed.add(index)
                upload.expires = time.monotonic() + self._ttl
            complete = True
        except OSError:
            raise _invalid() from None
        finally:
            with self._lock:
                upload.writing = False
                upload.pins -= 1
                if not complete:
                    upload.deleted = True
                self._clean(upload_id, upload)

    def _check_directory(self, directory: Path) -> None:
        if not stat.S_ISDIR(directory.lstat().st_mode) or directory.is_symlink():
            raise _invalid()

    def _mkdir(self, directory: Path) -> None:
        directory.mkdir(mode=0o700, exist_ok=True)
        self._check_directory(directory)

    def request(self, upload_id: str) -> CustomModelRequest:
        with self._lock:
            upload = self._get(upload_id)
            if len(upload.completed) != len(upload.request.files) or upload.writing:
                raise CustomModelError(
                    "custom_model_upload_incomplete",
                    "The folder upload is not complete.",
                )
            try:
                self._check_directory(upload.directory)
                for item in upload.request.files:
                    path = upload.directory / item.name
                    for parent in path.relative_to(upload.directory).parents:
                        self._check_directory(upload.directory / parent)
                    info = path.lstat()
                    if (
                        not stat.S_ISREG(info.st_mode)
                        or info.st_size != item.size_bytes
                    ):
                        raise _invalid()
            except OSError:
                raise _invalid() from None
            metadata = upload.request
            upload.expires = time.monotonic() + self._ttl
            return CustomModelRequest(
                source_type="folder",
                source=str(upload.directory),
                engine=metadata.engine,
                family=metadata.family,
                display_name=metadata.display_name,
                license=metadata.license,
                file_roles=dict(metadata.file_roles),
            )

    @contextmanager
    def hold(self, upload_id: str) -> Generator[None]:
        with self._lock:
            upload = self._get(upload_id)
            self.request(upload_id)
            upload.pins += 1
        try:
            yield
        finally:
            with self._lock:
                upload.pins -= 1
                self._clean(upload_id, upload)

    def hold_source(self, source: Path) -> AbstractContextManager[None]:
        # Do not resolve links: an expired owned path must never become an external one.
        try:
            relative = source.absolute().relative_to(self._root)
        except ValueError:
            return nullcontext()
        if not relative.parts or not re.fullmatch(r"[a-f0-9]{32}", relative.parts[0]):
            raise _expired()
        return self.hold(relative.parts[0])

    def discard(self, upload_id: str) -> None:
        with self._lock:
            upload = self._uploads.get(upload_id)
            if upload is not None:
                upload.deleted = True
                self._clean(upload_id, upload)

    def expire(self) -> None:
        with self._lock:
            for token, upload in list(self._uploads.items()):
                if time.monotonic() >= upload.expires:
                    upload.deleted = True
                self._clean(token, upload)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for token in tuple(self._uploads):
                self.discard(token)

    def _clean(self, token: str, upload: _Upload) -> None:
        if upload.deleted and upload.pins == 0:
            try:
                self._check_directory(self._root)
                self._check_directory(upload.directory)
                shutil.rmtree(upload.directory)
            except FileNotFoundError:
                pass
            except OSError:
                raise _invalid() from None
            self._uploads.pop(token, None)
