"""Explicit custom-model sources, previews and isolated load validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from voz.application.ports.model_installation import CancelCheck, ProgressCallback
from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.domain.entities.voice import Voice


class CustomModelError(Exception):
    """Stable, path-free import failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.user_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class CustomModelRequest:
    source_type: str
    source: str = field(repr=False)
    engine: str
    family: str
    display_name: str
    license: str = "unknown"
    revision: str = "main"
    file_roles: dict[str, str] = field(default_factory=dict[str, str])


@dataclass(frozen=True, slots=True)
class CustomModelFile:
    name: str
    size_bytes: int
    sha256: str | None = None
    url: str | None = field(default=None, repr=False)
    local_path: Path | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class CustomModelPreview:
    id: str
    descriptor: ModelDescriptor
    family: str
    license: str
    size_bytes: int
    file_count: int


@dataclass(frozen=True, slots=True)
class CustomModelPlan:
    preview: CustomModelPreview
    files: tuple[CustomModelFile, ...] = field(repr=False)
    file_roles: dict[str, str] = field(default_factory=dict[str, str], repr=False)


@dataclass(frozen=True, slots=True)
class CustomValidation:
    voices: tuple[Voice, ...] = ()
    languages: tuple[str, ...] = ()


class CustomModelValidator(Protocol):
    def validate(
        self,
        directory: Path,
        engine: str,
        family: str,
        *,
        file_roles: dict[str, str],
        cancelled: CancelCheck,
    ) -> CustomValidation: ...


class CustomModelBackend(Protocol):
    def prepare(self, request: CustomModelRequest) -> CustomModelPlan: ...

    def stage(
        self,
        plan: CustomModelPlan,
        *,
        progress: ProgressCallback | None,
        cancelled: CancelCheck,
    ) -> Path: ...

    def publish(
        self,
        plan: CustomModelPlan,
        directory: Path,
        validation: CustomValidation,
        *,
        cancelled: CancelCheck,
    ) -> ModelDescriptor: ...

    def discard(self, directory: Path) -> None: ...
