"""Imported media identity and safe metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from voz.domain.entities._validation import (
    require_aware_datetime,
    require_non_blank,
    require_positive_int,
    require_uuid,
)

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", re.ASCII)


@dataclass(frozen=True, slots=True)
class MediaAsset:
    """An immutable original's identity and UI-safe descriptive metadata.

    ``id`` identifies the domain entity and ``content_sha256`` identifies the
    original bytes. Storage locations deliberately belong to infrastructure and
    are not represented here.
    """

    project_id: UUID
    content_sha256: str
    display_name: str
    size_bytes: int
    id: UUID = field(default_factory=uuid4, kw_only=True)
    media_type: str | None = field(default=None, kw_only=True)
    duration_ms: int | None = field(default=None, kw_only=True)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC),
        kw_only=True,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_uuid(self.id, field="id"))
        object.__setattr__(
            self,
            "project_id",
            require_uuid(self.project_id, field="project_id"),
        )

        digest = require_non_blank(self.content_sha256, field="content_sha256")
        if _SHA256_PATTERN.fullmatch(digest) is None:
            raise ValueError("content_sha256 must be a lowercase SHA-256 digest")
        object.__setattr__(self, "content_sha256", digest)

        name = require_non_blank(self.display_name, field="display_name")
        if name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError("display_name must be a filename, not a path")
        object.__setattr__(self, "display_name", name)

        object.__setattr__(
            self,
            "size_bytes",
            require_positive_int(self.size_bytes, field="size_bytes"),
        )
        if self.duration_ms is not None:
            object.__setattr__(
                self,
                "duration_ms",
                require_positive_int(self.duration_ms, field="duration_ms"),
            )

        if self.media_type is not None:
            media_type = require_non_blank(self.media_type, field="media_type")
            media_family, separator, media_subtype = media_type.partition("/")
            if (
                not separator
                or not media_family
                or not media_subtype
                or media_type.count("/") != 1
            ):
                raise ValueError("media_type must use the type/subtype form")
            object.__setattr__(self, "media_type", media_type.lower())

        object.__setattr__(
            self,
            "created_at",
            require_aware_datetime(self.created_at, field="created_at"),
        )
