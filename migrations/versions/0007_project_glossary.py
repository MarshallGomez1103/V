"""Add per-project glossaries and the quality profile/glossary of a job.

``project_glossaries`` is a new table (one row per project, JSON list of terms).
``profile_json`` and ``glossary_json`` are nullable columns on
``transcription_job_selections``: ``NULL`` means the job predates profiles and
keeps the engine defaults. Existing rows are never rewritten.

Revision ID: 0007_project_glossary
Revises: 0006_segment_quality
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_project_glossary"
down_revision: str | Sequence[str] | None = "0006_segment_quality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the glossary table and add nullable selection columns in place."""
    op.create_table(
        "project_glossaries",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("terms_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_glossaries_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("project_id", name=op.f("pk_project_glossaries")),
    )
    # Plain ADD COLUMN (no batch rebuild): the selections table keeps its rows.
    op.add_column(
        "transcription_job_selections",
        sa.Column("profile_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "transcription_job_selections",
        sa.Column("glossary_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop glossaries and the stored profile/glossary (jobs fall back to defaults)."""
    # Plain DROP COLUMN, as in 0006: nothing indexes or references these columns.
    op.drop_column("transcription_job_selections", "glossary_json")
    op.drop_column("transcription_job_selections", "profile_json")
    op.drop_table("project_glossaries")
