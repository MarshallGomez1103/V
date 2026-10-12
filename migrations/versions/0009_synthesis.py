"""Add speech synthesis persistence (ADR-0010).

``synthesis_jobs`` holds the job state machine, chunk progress and a flat copy
of the ``SynthesisRequest``. ``synthesized_audio`` holds the stored result of a
completed job (path relative to V's synthesis storage, sizes, sha256) and is
removed with its job. Both tables are new: no existing row is touched.

Revision ID: 0009_synthesis
Revises: 0008_job_stage_prompt
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_synthesis"
down_revision: str | Sequence[str] | None = "0008_job_stage_prompt"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the synthesis tables and the history/recovery index."""
    op.create_table(
        "synthesis_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("chunks_done", sa.Integer(), nullable=False),
        sa.Column("chunks_total", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.String(length=40), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("provider_id", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("model_revision", sa.Text(), nullable=True),
        sa.Column("voice_id", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("speed", sa.Float(), nullable=False),
        sa.Column("output_format", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "chunks_total >= 1",
            name=op.f("ck_synthesis_jobs_chunks_total_positive"),
        ),
        sa.CheckConstraint(
            "chunks_done >= 0 AND chunks_done <= chunks_total",
            name=op.f("ck_synthesis_jobs_chunks_done_bounded"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_synthesis_jobs")),
    )
    op.create_index(
        op.f("ix_synthesis_jobs_state_created_at"),
        "synthesis_jobs",
        ["state", "created_at"],
        unique=False,
    )
    op.create_table(
        "synthesized_audio",
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("sample_rate", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "duration_ms > 0",
            name=op.f("ck_synthesized_audio_duration_ms_positive"),
        ),
        sa.CheckConstraint(
            "sample_rate > 0",
            name=op.f("ck_synthesized_audio_sample_rate_positive"),
        ),
        sa.CheckConstraint(
            "chunk_count > 0",
            name=op.f("ck_synthesized_audio_chunk_count_positive"),
        ),
        sa.CheckConstraint(
            "size_bytes > 0",
            name=op.f("ck_synthesized_audio_size_bytes_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["synthesis_jobs.id"],
            name=op.f("fk_synthesized_audio_job_id_synthesis_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("job_id", name=op.f("pk_synthesized_audio")),
    )


def downgrade() -> None:
    """Drop the synthesis tables (history and audio rows are lost)."""
    op.drop_table("synthesized_audio")
    op.drop_index(
        op.f("ix_synthesis_jobs_state_created_at"), table_name="synthesis_jobs"
    )
    op.drop_table("synthesis_jobs")
