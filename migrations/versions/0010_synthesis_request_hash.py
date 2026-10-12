"""Index synthesis jobs by the hash of their request (V2-06b).

``synthesis_jobs`` gains a nullable ``request_hash`` and an index on
``(request_hash, state)`` so ``CreateSynthesisJob`` can find an identical earlier
job without scanning the history.

Existing rows are backfilled with the same ``request_hash`` function the use case
uses at runtime (imported, so the two cannot drift). A row whose stored request
no longer validates keeps ``NULL``: it is simply never offered for reuse.

Revision ID: 0010_synthesis_request_hash
Revises: 0009_synthesis
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from voz.application.synthesis.create_synthesis_job import request_hash
from voz.domain.entities.synthesis_request import (
    SynthesisOutputFormat,
    SynthesisRequest,
)

revision: str = "0010_synthesis_request_hash"
down_revision: str | Sequence[str] | None = "0009_synthesis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_synthesis_jobs_request_hash_state"


def upgrade() -> None:
    """Add the column, backfill existing rows, then create the lookup index."""
    op.add_column(
        "synthesis_jobs", sa.Column("request_hash", sa.String(64), nullable=True)
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, text, provider_id, model_id, model_revision, voice_id,"
            " language, speed, output_format FROM synthesis_jobs"
        )
    ).mappings()
    for row in rows.all():
        try:
            request = SynthesisRequest(
                text=row["text"],
                provider_id=row["provider_id"],
                model_id=row["model_id"],
                voice_id=row["voice_id"],
                model_revision=row["model_revision"],
                language=row["language"],
                speed=row["speed"],
                output_format=SynthesisOutputFormat(row["output_format"]),
            )
        except (TypeError, ValueError):
            continue
        connection.execute(
            sa.text("UPDATE synthesis_jobs SET request_hash = :hash WHERE id = :id"),
            {"hash": request_hash(request), "id": row["id"]},
        )
    op.create_index(
        op.f(_INDEX), "synthesis_jobs", ["request_hash", "state"], unique=False
    )


def downgrade() -> None:
    """Drop the index and the column (the hashes are recomputable)."""
    op.drop_index(op.f(_INDEX), table_name="synthesis_jobs")
    op.drop_column("synthesis_jobs", "request_hash")
