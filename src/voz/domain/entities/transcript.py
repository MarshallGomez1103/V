"""Canonical transcript identity and invariants."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from voz.domain.entities._validation import (
    require_aware_datetime,
    require_non_blank,
    require_uuid,
)


@dataclass(frozen=True, slots=True)
class Transcript:
    """The canonical transcript associated with exactly one media asset."""

    project_id: UUID
    media_asset_id: UUID
    id: UUID = field(default_factory=uuid4, kw_only=True)
    language: str | None = field(default=None, kw_only=True)
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
        object.__setattr__(
            self,
            "media_asset_id",
            require_uuid(self.media_asset_id, field="media_asset_id"),
        )
        if self.language is not None:
            object.__setattr__(
                self,
                "language",
                require_non_blank(self.language, field="language"),
            )
        object.__setattr__(
            self,
            "created_at",
            require_aware_datetime(self.created_at, field="created_at"),
        )
