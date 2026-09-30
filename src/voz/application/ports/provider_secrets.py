"""Port for cloud provider API keys; implementations keep them out of SQLite/logs."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol


class SecretsFailureCode(StrEnum):
    """Stable codes; messages never contain the key or host paths."""

    FILE_INSECURE = "secrets_file_insecure"
    FILE_INVALID = "secrets_file_invalid"
    KEY_INVALID = "secrets_key_invalid"
    WRITE_FAILED = "secrets_write_failed"


class SecretsError(RuntimeError):
    def __init__(self, code: SecretsFailureCode, user_message: str) -> None:
        self.code = code
        self.user_message = user_message
        super().__init__(user_message)


class ProviderSecretsPort(Protocol):
    def get(self, provider_id: str) -> str | None: ...

    def configured(self, provider_id: str) -> bool: ...

    def set(self, provider_id: str, key: str) -> None: ...

    def delete(self, provider_id: str) -> None: ...


__all__ = ["ProviderSecretsPort", "SecretsError", "SecretsFailureCode"]
