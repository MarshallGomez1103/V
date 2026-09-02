"""Project aggregate identity and invariants."""

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
class Project:
    """A user workspace that owns media and transcripts."""

    name: str
    id: UUID = field(default_factory=uuid4, kw_only=True)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC),
        kw_only=True,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_uuid(self.id, field="id"))
        object.__setattr__(self, "name", require_non_blank(self.name, field="name"))
        object.__setattr__(
            self,
            "created_at",
            require_aware_datetime(self.created_at, field="created_at"),
        )
