"""Add segment editing columns (speaker, edited flag, revision, original text).

Revision ID: 0004_segment_editing
Revises: 0003_job_selections
"""

from collections.abc import Generator, Sequence
from contextlib import contextmanager

import sqlalchemy as sa
from alembic import op
from alembic.operations import BatchOperations

revision: str = "0004_segment_editing"
down_revision: str | Sequence[str] | None = "0003_job_selections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SPEAKER_FK = "fk_segments_speaker_id_speakers"


@contextmanager
def _recreating_segments() -> Generator[BatchOperations]:
    """Batch-alter ``segments`` without losing ``words``.

    SQLite rebuilds the table by dropping the original; with foreign keys ON that
    drop cascades into ``words``, so the rows are parked and restored around it.
    """
    op.execute("CREATE TABLE _words_backup AS SELECT * FROM words")
    with op.batch_alter_table("segments") as batch:
        yield batch
    op.execute("INSERT INTO words SELECT * FROM _words_backup")
    op.execute("DROP TABLE _words_backup")


def upgrade() -> None:
    """Add editable-transcript columns; existing rows stay pristine."""
    with _recreating_segments() as batch:
        batch.add_column(sa.Column("speaker_id", sa.String(length=36), nullable=True))
        batch.add_column(
            sa.Column("edited", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(
            sa.Column("revision", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("original_text", sa.Text(), nullable=True))
        batch.create_foreign_key(
            op.f(_SPEAKER_FK),
            "speakers",
            ["speaker_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Drop the editing columns (edits and speaker assignments are lost)."""
    with _recreating_segments() as batch:
        batch.drop_constraint(op.f(_SPEAKER_FK), type_="foreignkey")
        batch.drop_column("original_text")
        batch.drop_column("revision")
        batch.drop_column("edited")
        batch.drop_column("speaker_id")
