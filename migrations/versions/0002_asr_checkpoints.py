"""Add atomic ASR chunk checkpoints.

Revision ID: 0002_asr_checkpoints
Revises: 0001_initial_schema
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_asr_checkpoints"
down_revision: str | Sequence[str] | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the recoverable chunk checkpoint table."""
    op.create_table(
        "transcription_checkpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_index", sa.BigInteger(), nullable=False),
        sa.Column("process_start_ms", sa.BigInteger(), nullable=False),
        sa.Column("process_end_ms", sa.BigInteger(), nullable=False),
        sa.Column("owned_start_ms", sa.BigInteger(), nullable=False),
        sa.Column("owned_end_ms", sa.BigInteger(), nullable=False),
        sa.Column("provider_id", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("model_source", sa.Text(), nullable=True),
        sa.Column("model_revision", sa.Text(), nullable=True),
        sa.Column("requested_language", sa.Text(), nullable=True),
        sa.Column("segments_json", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("job_progress", sa.Float(), nullable=False),
        sa.Column("completed_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "chunk_index >= 0",
            name=op.f("ck_transcription_checkpoints_chunk_index_non_negative"),
        ),
        sa.CheckConstraint(
            "owned_end_ms <= process_end_ms",
            name=op.f("ck_transcription_checkpoints_process_contains_owned_end"),
        ),
        sa.CheckConstraint(
            "process_start_ms <= owned_start_ms",
            name=op.f("ck_transcription_checkpoints_process_contains_owned_start"),
        ),
        sa.CheckConstraint(
            "process_start_ms >= 0",
            name=op.f("ck_transcription_checkpoints_process_start_non_negative"),
        ),
        sa.CheckConstraint(
            "progress > 0.0 AND progress <= 1.0",
            name=op.f("ck_transcription_checkpoints_progress_bounded"),
        ),
        sa.CheckConstraint(
            "job_progress > 0.0 AND job_progress <= 1.0",
            name=op.f("ck_transcription_checkpoints_job_progress_bounded"),
        ),
        sa.CheckConstraint(
            "owned_start_ms < owned_end_ms",
            name=op.f("ck_transcription_checkpoints_owned_offsets_increasing"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["transcription_jobs.id"],
            name=op.f("fk_transcription_checkpoints_job_id_transcription_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transcription_checkpoints")),
        sa.UniqueConstraint(
            "job_id",
            "chunk_index",
            name=op.f("uq_checkpoint_job_chunk"),
        ),
    )
    op.create_index(
        op.f("ix_transcription_checkpoints_job_id"),
        "transcription_checkpoints",
        ["job_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove ASR checkpoints without changing existing job rows."""
    op.drop_index(
        op.f("ix_transcription_checkpoints_job_id"),
        table_name="transcription_checkpoints",
    )
    op.drop_table("transcription_checkpoints")
