"""Metadata for browser-selected model files; no browser host paths."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CustomModelUploadFile:
    name: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class CustomModelUploadRequest:
    engine: str
    family: str
    display_name: str
    files: tuple[CustomModelUploadFile, ...]
    license: str = "unknown"
    file_roles: dict[str, str] = field(default_factory=dict[str, str])


@dataclass(frozen=True, slots=True)
class CustomModelUploadReceipt:
    id: str
    total_bytes: int
    file_count: int
