"""Add optional diarization to job selections.

``diarization_json`` holds the requested speaker hint (``NULL`` = disabled) and
``diarization_error_code`` the stable code of a failed diarization whose
transcript was kept. Both live in ``transcription_job_selections`` so the job
state machine and its table stay untouched.

Revision ID: 0005_job_diarization
Revises: 0004_segment_editing
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_job_diarization"
down_revision: str | Sequence[str] | None = "0004_segment_editing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable columns in place; existing selections stay valid."""
    # Plain ADD COLUMN: SQLite does not rebuild the table, so nothing cascades.
    op.add_column(
        "transcription_job_selections",
        sa.Column("diarization_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "transcription_job_selections",
        sa.Column("diarization_error_code", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop the diarization columns (requests and errors are lost)."""
    # Nothing references this table, so the batch rebuild cannot cascade.
    with op.batch_alter_table("transcription_job_selections") as batch:
        batch.drop_column("diarization_error_code")
        batch.drop_column("diarization_json")
