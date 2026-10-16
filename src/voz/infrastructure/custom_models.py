"""Safe metadata discovery, owned staging and live custom-model registration."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import stat
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import cast
from urllib.parse import quote, urlsplit
from uuid import uuid4

from voz.application.ports.custom_models import (
    CustomModelError,
    CustomModelFile,
    CustomModelPlan,
    CustomModelPreview,
    CustomModelRequest,
    CustomValidation,
)
from voz.application.ports.model_installation import (
    CancelCheck,
    ModelFile,
    ProgressCallback,
)
from voz.application.ports.transcription import TranscriptionError
from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.voice import Voice
from voz.infrastructure.asr.catalog import faster_whisper_catalog
from voz.infrastructure.asr.sherpa_onnx_options import (
    SHERPA_ONNX_CAPABILITIES,
    SHERPA_ONNX_PROFILE,
    whisper_files,
)
from voz.infrastructure.asr.sherpa_onnx_options import (
    runtime_available as sherpa_asr_runtime_available,
)
from voz.infrastructure.asr.whisper_cpp import locate_whisper_cli
from voz.infrastructure.asr.whisper_cpp_catalog import whisper_cpp_catalog
from voz.infrastructure.model_registry import ENGINE_CAPABILITIES, ManagedModel
from voz.infrastructure.model_storage import FileSystemModelStore
from voz.infrastructure.tts.families import discover_files, model_config
from voz.infrastructure.tts.model_store import extract_custom_archive
from voz.infrastructure.tts.subprocess_provider import TtsModelManifest

_FAMILIES = {
    "faster-whisper": {"ctranslate2"},
    "whisper-cpp": {"ggml"},
    "sherpa-onnx-tts": {"kitten", "kokoro", "vits", "matcha"},
    "sherpa-onnx-asr": {"whisper"},
}
_ASR_FILES = {
    "model.bin",
    "config.json",
    "tokenizer.json",
    "vocabulary.txt",
    "vocabulary.json",
    "preprocessor_config.json",
    "tokenizer_config.json",
}
_MAX_BYTES = 16 * 1024**3
_MAX_FILES = 10_000


def _invalid() -> CustomModelError:
    return CustomModelError(
        "custom_model_invalid", "The selected model files or metadata are not valid."
    )


def _check_cancelled(cancelled: CancelCheck) -> None:
    if cancelled():
        raise CustomModelError(
            "model_installation_cancelled", "The import was cancelled."
        )


def safe_relative(name: str) -> bool:
    parts = PurePosixPath(name).parts
    return (
        bool(parts)
        and PurePosixPath(name).as_posix() == name
        and not name.startswith("/")
        and ".." not in parts
        and all(part not in {".", ""} and ":" not in part for part in parts)
        and "\\" not in name
        and len(name) <= 512
        and not any(ord(ch) < 32 for ch in name)
    )


def allowed_file(engine: str, name: str) -> bool:
    if not safe_relative(name):
        return False
    path = PurePosixPath(name)
    if engine == "sherpa-onnx-asr":
        return path.suffix in {".onnx", ".txt"} or name in {"LICENSE", "MODEL_CARD"}
    if engine == "faster-whisper":
        return name in _ASR_FILES
    if engine == "whisper-cpp":
        return (
            len(path.parts) == 1
            and path.name.startswith("ggml-")
            and path.suffix == ".bin"
        )
    if len(path.parts) > 1:
        return path.parts[0] in {"espeak-ng-data", "dict"} and path.suffix in {
            "",
            ".txt",
            ".dict",
        }
    return (
        path.suffix == ".onnx"
        or name in {"tokens.txt", "voices.bin", "LICENSE", "MODEL_CARD"}
        or (name.startswith("lexicon") and path.suffix == ".txt")
    )


def model_files(directory: Path, family: str, roles: dict[str, str]) -> dict[str, Path]:
    if family == "whisper":
        try:
            return whisper_files(directory, roles)
        except TranscriptionError:
            raise _invalid() from None
    if roles:
        if any(not safe_relative(name) for name in roles.values()):
            raise _invalid()
        files = {role: directory / name for role, name in roles.items()}
        model_config(family, files)
        return files
    return discover_files(family, directory)


def _runtime_available(engine: str) -> bool:
    if engine == "sherpa-onnx-asr":
        return sherpa_asr_runtime_available()
    if engine == "whisper-cpp":
        return locate_whisper_cli() is not None
    package = {
        "faster-whisper": "faster_whisper",
        "sherpa-onnx-tts": "sherpa_onnx",
    }.get(engine)
    return package is not None and importlib.util.find_spec(package) is not None


def _url(value: str) -> str:
    try:
        parts = urlsplit(value)
        _ = parts.port
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
            or any(ch.isspace() or ord(ch) < 32 for ch in value)
        ):
            raise _invalid()
    except ValueError:
        raise _invalid() from None
    return value


class CustomModelStore:
    def __init__(
        self,
        files: FileSystemModelStore,
        *,
        cache_root: Path,
        hf_base_url: str = "https://huggingface.co",
        timeout_seconds: float = 30.0,
        runtime_available: Callable[[str], bool] = _runtime_available,
    ) -> None:
        self._files = files
        self._staging = cache_root / "custom-models"
        self._hf = _url(hf_base_url).rstrip("/")
        self._timeout = timeout_seconds
        self._runtime_available = runtime_available

    def runtime_available(self, engine: str) -> bool:
        return self._runtime_available(engine)

    def prepare(self, request: CustomModelRequest) -> CustomModelPlan:
        if request.family not in _FAMILIES.get(request.engine, set()):
            raise CustomModelError(
                "custom_model_engine_unsupported",
                "Select an installed engine and a supported model family.",
            )
        if not self._runtime_available(request.engine):
            raise CustomModelError(
                "custom_model_runtime_unavailable",
                "The selected model engine is not installed.",
            )
        if (
            not request.license.strip()
            or len(request.license) > 512
            or any(ord(ch) < 32 for ch in request.license)
        ):
            raise _invalid()
        if any(not safe_relative(name) for name in request.file_roles.values()):
            raise _invalid()
        token = uuid4().hex
        source: str | None = None
        revision: str | None = None
        try:
            if request.source_type == "folder":
                items = self._folder(Path(request.source), request.engine)
            elif request.source_type == "url":
                url = _url(request.source)
                name = PurePosixPath(urlsplit(url).path).name
                if not (
                    (
                        request.engine == "whisper-cpp"
                        and allowed_file(request.engine, name)
                    )
                    or (
                        request.engine in {"sherpa-onnx-tts", "sherpa-onnx-asr"}
                        and name.endswith(".tar.bz2")
                    )
                ):
                    raise _invalid()
                items = (CustomModelFile(name, self._remote_size(url), url=url),)
            elif request.source_type == "huggingface":
                source, revision, items = self._huggingface(request)
            else:
                raise _invalid()
            total = sum(item.size_bytes for item in items)
            if not items or not 0 < total <= _MAX_BYTES or len(items) > _MAX_FILES:
                raise _invalid()
            descriptor = ModelDescriptor(
                provider_id=request.engine,
                model_id="custom-" + token,
                display_name=request.display_name,
                capabilities=SHERPA_ONNX_CAPABILITIES
                if request.engine == "sherpa-onnx-asr"
                else ENGINE_CAPABILITIES[request.engine],
                source=source,
                revision=revision,
                profile=faster_whisper_catalog()[0].descriptor.profile
                if request.engine == "faster-whisper"
                else whisper_cpp_catalog()[0].descriptor.profile
                if request.engine == "whisper-cpp"
                else SHERPA_ONNX_PROFILE
                if request.engine == "sherpa-onnx-asr"
                else None,
            )
        except (OSError, ValueError, TypeError):
            raise _invalid() from None
        preview = CustomModelPreview(
            token,
            descriptor,
            request.family,
            "unknown"
            if request.license.strip().lower() == "unknown"
            else "User-declared: " + request.license.strip(),
            total,
            len(items),
        )
        return CustomModelPlan(preview, items, dict(request.file_roles))

    def _folder(self, directory: Path, engine: str) -> tuple[CustomModelFile, ...]:
        if directory.is_symlink() or not directory.is_dir():
            raise _invalid()
        found: list[CustomModelFile] = []
        for count, path in enumerate(directory.rglob("*")):
            if count >= _MAX_FILES or path.is_symlink():
                raise _invalid()
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                continue
            if not stat.S_ISREG(info.st_mode):
                raise _invalid()
            name = path.relative_to(directory).as_posix()
            if allowed_file(engine, name) and info.st_size > 0:
                found.append(CustomModelFile(name, info.st_size, local_path=path))
        return tuple(sorted(found, key=lambda item: item.name))

    def _remote_size(self, url: str) -> int:
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, method="HEAD"), timeout=self._timeout
            ) as response:
                size = int(response.headers.get("Content-Length", "0"))
        except (OSError, ValueError, urllib.error.URLError):
            raise CustomModelError(
                "custom_model_metadata_unavailable",
                "The model size could not be determined before confirmation.",
            ) from None
        if not 0 < size <= _MAX_BYTES:
            raise _invalid()
        return size

    def _huggingface(
        self, request: CustomModelRequest
    ) -> tuple[str, str, tuple[CustomModelFile, ...]]:
        repo = request.source
        if repo.startswith("https://huggingface.co/"):
            repo = urlsplit(_url(repo)).path.strip("/")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise _invalid()
        ref = quote(request.revision, safe="")
        try:
            with urllib.request.urlopen(
                f"{self._hf}/api/models/{repo}/revision/{ref}?blobs=true",
                timeout=self._timeout,
            ) as response:
                raw = response.read(1_048_577)
                if len(raw) > 1_048_576:
                    raise _invalid()
                parsed: object = json.loads(raw)
                if not isinstance(parsed, dict):
                    raise _invalid()
                document = cast(dict[str, object], parsed)
            revision = document["sha"]
            if (
                not isinstance(revision, str)
                or re.fullmatch("[0-9a-f]{40}", revision) is None
            ):
                raise _invalid()
            items: list[CustomModelFile] = []
            siblings = document["siblings"]
            if (
                not isinstance(siblings, list)
                or len(cast(list[object], siblings)) > _MAX_FILES
            ):
                raise _invalid()
            for raw_item in cast(list[object], siblings):
                if not isinstance(raw_item, dict):
                    raise _invalid()
                item = cast(dict[str, object], raw_item)
                name = item["rfilename"]
                if not isinstance(name, str) or not safe_relative(name):
                    raise _invalid()
                if not allowed_file(request.engine, name):
                    continue
                raw_lfs = item.get("lfs")
                if raw_lfs is not None and not isinstance(raw_lfs, dict):
                    raise _invalid()
                lfs: dict[str, object] = (
                    cast(dict[str, object], raw_lfs) if raw_lfs is not None else {}
                )
                size = item.get("size") or lfs.get("size")
                sha = lfs.get("sha256")
                if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
                    raise _invalid()
                if sha is not None and (
                    not isinstance(sha, str)
                    or re.fullmatch("[0-9a-f]{64}", sha) is None
                ):
                    raise _invalid()
                items.append(
                    CustomModelFile(
                        name,
                        size,
                        sha,
                        url=f"{self._hf}/{repo}/resolve/{revision}/"
                        f"{quote(name, safe='/')}",
                    )
                )
        except (OSError, ValueError, KeyError, TypeError):
            raise CustomModelError(
                "custom_model_metadata_unavailable",
                "The model repository metadata could not be read safely.",
            ) from None
        if len({item.name for item in items}) != len(items):
            raise _invalid()
        return repo, revision, tuple(items)

    def stage(
        self,
        plan: CustomModelPlan,
        *,
        progress: ProgressCallback | None,
        cancelled: CancelCheck,
    ) -> Path:
        self._files.require_custom_space(plan.preview.size_bytes)
        self._staging.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory = Path(
            tempfile.mkdtemp(prefix=plan.preview.id + "-", dir=self._staging)
        )
        total = plan.preview.size_bytes
        done = 0
        try:
            for item in plan.files:
                _check_cancelled(cancelled)
                target = directory / item.name
                target.parent.mkdir(parents=True, exist_ok=True)
                if item.local_path is not None:
                    if (
                        item.local_path.is_symlink()
                        or item.local_path.stat().st_size != item.size_bytes
                    ):
                        raise _invalid()
                    with (
                        item.local_path.open("rb") as source,
                        target.open("xb") as output,
                    ):
                        copied = 0
                        while block := source.read(1024 * 1024):
                            _check_cancelled(cancelled)
                            copied += len(block)
                            if copied > item.size_bytes:
                                raise _invalid()
                            output.write(block)
                            if progress:
                                progress(done + copied, total)
                    if copied != item.size_bytes:
                        raise _invalid()
                elif item.url is not None:
                    self._files.fetch_custom_file(
                        item.url,
                        target.parent,
                        ModelFile(target.name, item.size_bytes, item.sha256),
                        on_bytes=lambda count, base=done: (
                            progress(base + count, total) if progress else None
                        ),
                        cancelled=cancelled,
                    )
                else:
                    raise _invalid()
                done += item.size_bytes
            if len(plan.files) == 1 and plan.files[0].name.endswith(".tar.bz2"):
                archive = directory / plan.files[0].name
                extracted = directory / ".extracted"
                extract_custom_archive(
                    archive,
                    extracted,
                    lambda name: allowed_file(
                        plan.preview.descriptor.provider_id, name
                    ),
                    cancelled,
                )
                archive.unlink()
                for child in extracted.iterdir():
                    child.rename(directory / child.name)
                extracted.rmdir()
            engine = plan.preview.descriptor.provider_id
            if engine == "faster-whisper" and not {
                "model.bin",
                "config.json",
                "tokenizer.json",
            } <= {p.name for p in directory.iterdir()}:
                raise _invalid()
            if engine == "whisper-cpp":
                weights = list(directory.glob("ggml-*.bin"))
                if len(weights) != 1:
                    raise _invalid()
                weights[0].rename(
                    directory / f"ggml-{plan.preview.descriptor.model_id}.bin"
                )
            return directory
        except BaseException:
            self.discard(directory)
            raise

    def publish(
        self,
        plan: CustomModelPlan,
        directory: Path,
        validation: CustomValidation,
        *,
        cancelled: CancelCheck,
    ) -> ModelDescriptor:
        digests: list[dict[str, object]] = []
        for path in sorted(directory.rglob("*")):
            _check_cancelled(cancelled)
            if path.is_symlink():
                raise _invalid()
            if not path.is_file():
                continue
            digest = hashlib.sha256()
            with path.open("rb") as source:
                while block := source.read(1024 * 1024):
                    _check_cancelled(cancelled)
                    digest.update(block)
            digests.append(
                {
                    "name": path.relative_to(directory).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": digest.hexdigest(),
                }
            )
        content = hashlib.sha256(
            json.dumps(digests, sort_keys=True).encode()
        ).hexdigest()
        descriptor = plan.preview.descriptor
        if descriptor.provenance is None:
            descriptor = replace(
                descriptor,
                source=plan.files[0].url or "sha256:" + content,
                revision=content[:40],
            )
        metadata: dict[str, object] = {
            "family": plan.preview.family,
            "license": plan.preview.license,
            "files": digests,
            "file_roles": plan.file_roles,
            "voices": [
                {"id": v.id, "name": v.name, "languages": list(v.languages)}
                for v in validation.voices
            ],
            "languages": list(validation.languages),
        }
        _check_cancelled(cancelled)
        self._files.publish_custom(descriptor, directory, metadata, cancelled=cancelled)
        return descriptor

    def discard(self, directory: Path) -> None:
        if directory.exists():
            shutil.rmtree(directory)

    def _records(self) -> tuple[tuple[ModelDescriptor, dict[str, object]], ...]:
        records: list[tuple[ModelDescriptor, dict[str, object]]] = []
        for descriptor in self._files.registered_descriptors():
            if (
                not descriptor.model_id.startswith("custom-")
                or descriptor.provider_id not in _FAMILIES
            ):
                continue
            try:
                directory = self._files.resolve_path(descriptor)
                metadata = cast(
                    dict[str, object],
                    json.loads(
                        (directory / ".voz-custom.json").read_text(encoding="utf-8")
                    ),
                )
                if metadata["family"] not in _FAMILIES[descriptor.provider_id]:
                    continue
                license = metadata["license"]
                languages = metadata["languages"]
                voices = metadata["voices"]
                roles = metadata["file_roles"]
                if (
                    not isinstance(license, str)
                    or not license
                    or not isinstance(languages, list)
                    or not all(
                        isinstance(item, str) for item in cast(list[object], languages)
                    )
                    or not isinstance(voices, list)
                    or not isinstance(roles, dict)
                ):
                    continue
                if not all(
                    isinstance(key, str)
                    and isinstance(value, str)
                    and safe_relative(value)
                    for key, value in cast(dict[object, object], roles).items()
                ):
                    continue
                descriptor = replace(
                    descriptor,
                    capabilities=SHERPA_ONNX_CAPABILITIES
                    if descriptor.provider_id == "sherpa-onnx-asr"
                    else ENGINE_CAPABILITIES[descriptor.provider_id],
                    profile=faster_whisper_catalog()[0].descriptor.profile
                    if descriptor.provider_id == "faster-whisper"
                    else whisper_cpp_catalog()[0].descriptor.profile
                    if descriptor.provider_id == "whisper-cpp"
                    else SHERPA_ONNX_PROFILE
                    if descriptor.provider_id == "sherpa-onnx-asr"
                    else None,
                )
                records.append((descriptor, metadata))
            except (OSError, ValueError, TypeError, KeyError, TranscriptionError):
                continue
        return tuple(records)

    def managed_entries(self) -> tuple[ManagedModel, ...]:
        return tuple(
            ManagedModel(
                descriptor,
                (
                    ModelFile(
                        "custom-weights",
                        sum(
                            cast(int, item["size_bytes"])
                            for item in cast(list[dict[str, object]], metadata["files"])
                        ),
                        None,
                    ),
                ),
                str(metadata["license"]),
                len(cast(list[str], metadata["languages"])) > 1,
                kind="tts" if descriptor.provider_id == "sherpa-onnx-tts" else "asr",
                runtime_available=self._runtime_available(descriptor.provider_id),
            )
            for descriptor, metadata in self._records()
        )

    def list_models(self, capability: ModelCapability) -> tuple[ModelRegistration, ...]:
        return tuple(
            ModelRegistration(
                descriptor, InstallationStatus.REGISTERED, files_available=True
            )
            for descriptor, _ in self._records()
            if descriptor.supports(capability)
        )

    def manifest(self, model_id: str) -> TtsModelManifest | None:
        for descriptor, metadata in self._records():
            if (
                descriptor.model_id != model_id
                or descriptor.provider_id != "sherpa-onnx-tts"
            ):
                continue
            try:
                files = model_files(
                    self._files.resolve_path(descriptor),
                    str(metadata["family"]),
                    cast(dict[str, str], metadata["file_roles"]),
                )
                voices = tuple(
                    Voice(
                        str(v["id"]),
                        str(v["name"]),
                        tuple(cast(list[str], v["languages"])),
                    )
                    for v in cast(list[dict[str, object]], metadata["voices"])
                )
                return TtsModelManifest(
                    str(metadata["family"]),
                    files,
                    voices,
                    tuple(cast(list[str], metadata["languages"])),
                )
            except (OSError, ValueError, TypeError, KeyError):
                return None
        return None

    def is_installed(self, descriptor: ModelDescriptor) -> bool:
        return self._files.is_installed(descriptor)

    def disk_usage(self, descriptor: ModelDescriptor) -> int | None:
        return self._files.disk_usage(descriptor)

    def reclaimable_usage(self, descriptor: ModelDescriptor) -> int | None:
        return self._files.reclaimable_usage(descriptor)

    def remove(self, descriptor: ModelDescriptor) -> int:
        return self._files.remove(descriptor)


class CustomModelCatalog:
    def __init__(self, store: CustomModelStore, capability: ModelCapability) -> None:
        self._store, self._capability = store, capability

    def list_models(self) -> tuple[ModelRegistration, ...]:
        return self._store.list_models(self._capability)
