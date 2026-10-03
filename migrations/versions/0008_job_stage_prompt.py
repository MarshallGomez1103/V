"""Add per-stage job timing/progress and the style prompt of a selection.

``transcription_jobs`` gains ``started_at`` (first time the job left QUEUED),
``stage_started_at`` (when the current state began) and ``stage_progress``
(0..1 inside the current stage). ``transcription_job_selections`` gains
``prompt``, the optional style instruction handed to the ASR engine.

Existing rows are backfilled so the new fields make sense: jobs that already ran
get ``started_at = created_at``; every job gets ``stage_started_at = updated_at``.
Jobs interrupted after transcription had global progress 1.0 under the old
"progress = chunks" scheme; they are capped to the weighted scale (transcription
ends at 0.8, speakers at 0.98) so a recovered job never sits at 100 %.

Revision ID: 0008_job_stage_prompt
Revises: 0007_project_glossary
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_job_stage_prompt"
down_revision: str | Sequence[str] | None = "0007_project_glossary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable columns in place and backfill legacy rows."""
    op.add_column(
        "transcription_jobs", sa.Column("started_at", sa.String(40), nullable=True)
    )
    op.add_column(
        "transcription_jobs",
        sa.Column("stage_started_at", sa.String(40), nullable=True),
    )
    op.add_column(
        "transcription_jobs", sa.Column("stage_progress", sa.Float(), nullable=True)
    )
    op.add_column(
        "transcription_job_selections", sa.Column("prompt", sa.Text(), nullable=True)
    )
    op.execute(
        "UPDATE transcription_jobs SET started_at = created_at WHERE state != 'QUEUED'"
    )
    op.execute("UPDATE transcription_jobs SET stage_started_at = updated_at")
    op.execute(
        "UPDATE transcription_jobs SET progress = MIN(progress, 0.8) "
        "WHERE state IN ('ALIGNING', 'DIARIZING')"
    )
    op.execute(
        "UPDATE transcription_jobs SET progress = MIN(progress, 0.98) "
        "WHERE state IN ('MERGING', 'PERSISTING')"
    )


def downgrade() -> None:
    """Drop the new columns (timing and prompts are lost; progress stays)."""
    op.drop_column("transcription_job_selections", "prompt")
    op.drop_column("transcription_jobs", "stage_progress")
    op.drop_column("transcription_jobs", "stage_started_at")
    op.drop_column("transcription_jobs", "started_at")
