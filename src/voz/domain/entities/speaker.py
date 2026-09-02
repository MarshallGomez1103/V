"""Editable speaker identity in the domain model."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from voz.domain.entities._validation import (
    require_aware_datetime,
    require_non_blank,
    require_uuid,
)

_HEX_COLOR_PATTERN = re.compile(r"#[0-9a-f]{6}", re.ASCII)


def _require_hex_color(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("color must be a string")
    normalized = value.strip().lower()
    if _HEX_COLOR_PATTERN.fullmatch(normalized) is None:
        raise ValueError("color must use the #RRGGBB format")
    return normalized


@dataclass(frozen=True, slots=True)
class Speaker:
    """A project-owned, user-editable speaker identity."""

    project_id: UUID
    name: str
    color: str
    id: UUID = field(default_factory=uuid4, kw_only=True)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC),
        kw_only=True,
    )
    updated_at: datetime = field(
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
            "name",
            require_non_blank(self.name, field="name"),
        )
        object.__setattr__(self, "color", _require_hex_color(self.color))
        object.__setattr__(
            self,
            "created_at",
            require_aware_datetime(self.created_at, field="created_at"),
        )
        object.__setattr__(
            self,
            "updated_at",
            require_aware_datetime(self.updated_at, field="updated_at"),
        )
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be before created_at")

    def rename(
        self,
        name: str,
        *,
        updated_at: datetime | None = None,
    ) -> Speaker:
        """Return a renamed snapshot while preserving the speaker identity."""

        changed_at = datetime.now(UTC) if updated_at is None else updated_at
        changed_at = require_aware_datetime(changed_at, field="updated_at")
        if changed_at < self.created_at:
            raise ValueError("updated_at cannot be before created_at")
        if changed_at < self.updated_at:
            raise ValueError("updated_at cannot be before current updated_at")
        return replace(self, name=name, updated_at=changed_at)
