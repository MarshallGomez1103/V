"""Add the per-job clip and the per-project transcription queue (ADR-0015).

``transcription_job_selections`` gains the nullable ``clip_start_ms`` and
``clip_end_ms``: both NULL means the whole recording, which is how every existing
row reads. ``transcription_queues`` and ``transcription_queue_items`` are new:
one queue per "transcribe project" request, with one ordered item per job. Queues
go with their project and items with their queue or job; jobs outlive a queue.

Revision ID: 0011_transcription_clip_and_queue
Revises: 0010_synthesis_request_hash
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_transcription_clip_and_queue"
down_revision: str | Sequence[str] | None = "0010_synthesis_request_hash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the clip columns and create the queue tables."""
    op.add_column(
        "transcription_job_selections",
        sa.Column("clip_start_ms", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "transcription_job_selections",
        sa.Column("clip_end_ms", sa.BigInteger(), nullable=True),
    )
    op.create_table(
        "transcription_queues",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("skipped_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_transcription_queues_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transcription_queues")),
    )
    op.create_index(
        op.f("ix_transcription_queues_project_id"),
        "transcription_queues",
        ["project_id"],
        unique=False,
    )
    op.create_table(
        "transcription_queue_items",
        sa.Column("queue_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.CheckConstraint(
            "position >= 0",
            name=op.f("ck_transcription_queue_items_position_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["queue_id"],
            ["transcription_queues.id"],
            name=op.f("fk_transcription_queue_items_queue_id_transcription_queues"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["transcription_jobs.id"],
            name=op.f("fk_transcription_queue_items_job_id_transcription_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "queue_id", "position", name=op.f("pk_transcription_queue_items")
        ),
        sa.UniqueConstraint("job_id", name=op.f("uq_transcription_queue_items_job_id")),
    )


def downgrade() -> None:
    """Drop the queue tables and the clip columns (queues and clips are lost)."""
    op.drop_table("transcription_queue_items")
    op.drop_index(
        op.f("ix_transcription_queues_project_id"), table_name="transcription_queues"
    )
    op.drop_table("transcription_queues")
    op.drop_column("transcription_job_selections", "clip_end_ms")
    op.drop_column("transcription_job_selections", "clip_start_ms")
