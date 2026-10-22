"""User-configured OpenAI-compatible servers (V4-04, ADR-0010 section 5).

An endpoint is a ``base_url`` (including ``/v1``), an optional key (kept by
``ProviderSecretsPort``, never here) and the model ids and voices the user
declares. A ``base_url`` whose host is loopback is **local**; any other host
is **cloud** and is saved only with the user's explicit ``cloud_consent``
(ADR-0006). Nothing here performs I/O.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol, cast
from unicodedata import category
from urllib.parse import urlsplit

MAX_MODELS: Final = 32
MAX_VOICES: Final = 64
_ENDPOINT_ID = re.compile(r"[0-9a-f]{12}", re.ASCII)
SECRET_PREFIX: Final = "openai-compatible."


class EndpointFailureCode(StrEnum):
    INVALID = "endpoint_invalid"
    NOT_FOUND = "endpoint_not_found"
    CONSENT_REQUIRED = "endpoint_cloud_consent_required"
    FILE_INSECURE = "endpoints_file_insecure"
    FILE_INVALID = "endpoints_file_invalid"
    WRITE_FAILED = "endpoints_write_failed"


class EndpointError(Exception):
    """Typed configuration failure with a user-safe message (never the key)."""

    def __init__(self, code: EndpointFailureCode, user_message: str) -> None:
        self.code = code
        self.user_message = user_message
        super().__init__(user_message)


def _invalid(message: str) -> EndpointError:
    return EndpointError(EndpointFailureCode.INVALID, message)


def is_loopback_url(base_url: str) -> bool:
    """``True`` only for ``localhost``, 127.0.0.0/8 and ``::1``."""
    try:
        host = urlsplit(base_url).hostname
    except ValueError:
        return False
    if host is None:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def normalize_base_url(value: object) -> str:
    """``http(s)://host[:port][/path]`` without credentials, query or trailing /.

    ``http://`` is accepted only for loopback hosts.
    """
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise _invalid("The server URL must be 1-512 characters.")
    url = value.strip().rstrip("/")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise _invalid("The server URL is not valid.") from None
    del port
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or any(category(ch).startswith("C") or ch.isspace() for ch in url)
    ):
        raise _invalid(
            "The server URL must be http(s)://host[:port]/path, without "
            "credentials, query or fragment."
        )
    if parts.scheme == "http" and not is_loopback_url(url):
        raise _invalid(
            "Remote servers must use https://; plain http:// is only allowed "
            "for localhost."
        )
    return url


def origin(base_url: str) -> tuple[str, str, int]:
    """``(scheme, host, port)`` of a normalized URL: what a saved key belongs to."""
    parts = urlsplit(base_url)
    default = 443 if parts.scheme == "https" else 80
    return parts.scheme, parts.hostname or "", parts.port or default


def _text(value: object, *, what: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > maximum
        or any(category(ch).startswith("C") for ch in value)
    ):
        raise _invalid(f"Each {what} must be 1-{maximum} visible characters.")
    return value


def _names(values: object, *, what: str, maximum: int) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        raise _invalid(f"The {what} list is not valid.")
    items = tuple(
        _text(item, what=what, maximum=242 if what == "model" else 255)
        for item in cast(list[object], values)
    )
    if len(items) > maximum or len(set(items)) != len(items):
        raise _invalid(f"Up to {maximum} different {what} values are allowed.")
    return items


@dataclass(frozen=True, slots=True)
class CompatibleEndpoint:
    """One validated server. ``cloud_consent`` is recorded, never inferred."""

    id: str
    name: str
    base_url: str
    stt_models: tuple[str, ...] = ()
    tts_models: tuple[str, ...] = ()
    tts_voices: tuple[str, ...] = ()
    cloud_consent: bool = False

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.id), str) or not _ENDPOINT_ID.fullmatch(
            self.id
        ):
            raise _invalid("The endpoint id is not valid.")
        _text(self.name, what="name", maximum=80)
        object.__setattr__(self, "base_url", normalize_base_url(self.base_url))
        for field, what, maximum in (
            ("stt_models", "model", MAX_MODELS),
            ("tts_models", "model", MAX_MODELS),
            ("tts_voices", "voice", MAX_VOICES),
        ):
            object.__setattr__(
                self,
                field,
                _names(getattr(self, field), what=what, maximum=maximum),
            )
        if not self.stt_models and not self.tts_models:
            raise _invalid("Declare at least one transcription or speech model.")
        if self.tts_models and not self.tts_voices:
            raise _invalid("Speech models need at least one voice.")
        if type(self.cloud_consent) is not bool:
            raise _invalid("cloud_consent must be a boolean.")
        if self.cloud and not self.cloud_consent:
            raise EndpointError(
                EndpointFailureCode.CONSENT_REQUIRED,
                "This server is not on this computer: confirm that audio and "
                "text will be sent to it.",
            )

    @property
    def cloud(self) -> bool:
        return not is_loopback_url(self.base_url)

    @property
    def secret_id(self) -> str:
        """Key name in ``ProviderSecretsPort``."""
        return SECRET_PREFIX + self.id


class CompatibleEndpointStore(Protocol):
    """Persisted endpoints; every read is live (no restart after an edit)."""

    def list(self) -> tuple[CompatibleEndpoint, ...]: ...

    def get(self, endpoint_id: str) -> CompatibleEndpoint | None: ...

    def save(self, endpoint: CompatibleEndpoint) -> None: ...

    def delete(self, endpoint_id: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class ConnectionCheck:
    """Outcome of ``GET {base_url}/models``; ``code`` explains a failure."""

    reachable: bool
    status: int | None = None
    models: tuple[str, ...] = ()
    code: str | None = None


class EndpointConnectionTester(Protocol):
    def check(self, endpoint: CompatibleEndpoint, key: str | None) -> ConnectionCheck:
        """Ask the server for its models with a short timeout; never raises."""
        ...


__all__ = [
    "MAX_MODELS",
    "MAX_VOICES",
    "SECRET_PREFIX",
    "CompatibleEndpoint",
    "CompatibleEndpointStore",
    "ConnectionCheck",
    "EndpointConnectionTester",
    "EndpointError",
    "EndpointFailureCode",
    "is_loopback_url",
    "normalize_base_url",
    "origin",
]
