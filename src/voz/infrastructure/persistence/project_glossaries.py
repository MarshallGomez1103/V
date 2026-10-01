"""SQLite adapter for the per-project glossary (S13.01)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import Engine, delete, select
from sqlalchemy.dialects.sqlite import insert

from voz.infrastructure.persistence.schema import project_glossaries


class SqliteProjectGlossaryRepository:
    """One JSON list of terms per project; no row means an empty glossary."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get(self, project_id: UUID) -> tuple[str, ...]:
        with self._engine.connect() as connection:
            raw = connection.execute(
                select(project_glossaries.c.terms_json).where(
                    project_glossaries.c.project_id == str(project_id)
                )
            ).scalar_one_or_none()
        if raw is None:
            return ()
        terms: object = json.loads(raw)
        if not isinstance(terms, list) or not all(
            isinstance(term, str) for term in cast(list[object], terms)
        ):
            raise TypeError("persisted glossary must be a list of strings")
        return tuple(cast(list[str], terms))

    def put(self, project_id: UUID, terms: tuple[str, ...]) -> None:
        with self._engine.begin() as connection:
            if not terms:
                connection.execute(
                    delete(project_glossaries).where(
                        project_glossaries.c.project_id == str(project_id)
                    )
                )
                return
            values = {
                "project_id": str(project_id),
                "terms_json": json.dumps(list(terms), ensure_ascii=False),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            connection.execute(
                insert(project_glossaries)
                .values(values)
                .on_conflict_do_update(
                    index_elements=["project_id"],
                    set_={
                        "terms_json": values["terms_json"],
                        "updated_at": values["updated_at"],
                    },
                )
            )


__all__ = ["SqliteProjectGlossaryRepository"]
