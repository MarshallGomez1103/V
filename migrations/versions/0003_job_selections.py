"""Add reproducible per-job selection snapshots.

Revision ID: 0003_job_selections
Revises: 0002_asr_checkpoints
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_job_selections"
down_revision: str | Sequence[str] | None = "0002_asr_checkpoints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the one-to-one job selection snapshot table."""
    op.create_table(
        "transcription_job_selections",
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("option_id", sa.Text(), nullable=False),
        sa.Column("provider_id", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("revision", sa.Text(), nullable=True),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("model_json", sa.Text(), nullable=False),
        sa.Column("execution_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["transcription_jobs.id"],
            name=op.f("fk_transcription_job_selections_job_id_transcription_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("job_id", name=op.f("pk_transcription_job_selections")),
    )


def downgrade() -> None:
    """Remove selection snapshots without touching job rows."""
    op.drop_table("transcription_job_selections")
