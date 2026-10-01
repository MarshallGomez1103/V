"""Add non-destructive quality hints to segments.

``quality_json`` holds ``{"flags": [...], "avg_logprob": x}`` next to the literal
text (S13.04/S13.05/S13.12); ``NULL`` means nothing was flagged. The text and
``original_text`` are never touched by this revision.

Revision ID: 0006_segment_quality
Revises: 0005_job_diarization
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_segment_quality"
down_revision: str | Sequence[str] | None = "0005_job_diarization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a nullable column in place; existing segments stay valid."""
    # Plain ADD COLUMN (no batch rebuild): dropping ``segments`` would cascade
    # into ``words`` (see 0004).
    op.add_column("segments", sa.Column("quality_json", sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop the hints (they are derived and recomputable); text and words stay."""
    # Plain DROP COLUMN for the same cascade reason; nothing indexes the column.
    op.drop_column("segments", "quality_json")
