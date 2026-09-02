"""Create the initial VOZ persistence schema.

Revision ID: 0001_initial_schema
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create every table, constraint, and index in the Core metadata."""

    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_table(
        "media_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms > 0",
            name=op.f("ck_media_assets_duration_ms_positive"),
        ),
        sa.CheckConstraint(
            "size_bytes > 0",
            name=op.f("ck_media_assets_size_bytes_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_media_assets_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_assets")),
    )
    op.create_index(
        op.f("ix_media_assets_content_sha256"),
        "media_assets",
        ["content_sha256"],
        unique=False,
    )
    op.create_index(
        op.f("ix_media_assets_project_id"),
        "media_assets",
        ["project_id"],
        unique=False,
    )
    op.create_table(
        "speakers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_speakers_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_speakers")),
    )
    op.create_index(
        op.f("ix_speakers_project_id"),
        "speakers",
        ["project_id"],
        unique=False,
    )
    op.create_table(
        "transcription_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("media_asset_id", sa.String(length=36), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "progress >= 0.0 AND progress <= 1.0",
            name=op.f("ck_transcription_jobs_progress_bounded"),
        ),
        sa.ForeignKeyConstraint(
            ["media_asset_id"],
            ["media_assets.id"],
            name=op.f("fk_transcription_jobs_media_asset_id_media_assets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_transcription_jobs_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transcription_jobs")),
    )
    op.create_index(
        op.f("ix_transcription_jobs_media_asset_id"),
        "transcription_jobs",
        ["media_asset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transcription_jobs_project_id"),
        "transcription_jobs",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transcription_jobs_state"),
        "transcription_jobs",
        ["state"],
        unique=False,
    )
    op.create_table(
        "transcripts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("media_asset_id", sa.String(length=36), nullable=False),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["media_asset_id"],
            ["media_assets.id"],
            name=op.f("fk_transcripts_media_asset_id_media_assets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_transcripts_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transcripts")),
    )
    op.create_index(
        op.f("ix_transcripts_media_asset_id"),
        "transcripts",
        ["media_asset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transcripts_project_id"),
        "transcripts",
        ["project_id"],
        unique=False,
    )
    op.create_table(
        "segments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("transcript_id", sa.String(length=36), nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=False),
        sa.Column("end_ms", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "end_ms > start_ms",
            name=op.f("ck_segments_offsets_increasing"),
        ),
        sa.CheckConstraint(
            "start_ms >= 0",
            name=op.f("ck_segments_start_ms_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["transcript_id"],
            ["transcripts.id"],
            name=op.f("fk_segments_transcript_id_transcripts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_segments")),
    )
    op.create_index(
        op.f("ix_segments_transcript_id"),
        "segments",
        ["transcript_id"],
        unique=False,
    )
    op.create_table(
        "speaker_turns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("transcript_id", sa.String(length=36), nullable=False),
        sa.Column("cluster_label", sa.Text(), nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=False),
        sa.Column("end_ms", sa.BigInteger(), nullable=False),
        sa.Column("speaker_id", sa.String(length=36), nullable=True),
        sa.CheckConstraint(
            "end_ms > start_ms",
            name=op.f("ck_speaker_turns_offsets_increasing"),
        ),
        sa.CheckConstraint(
            "start_ms >= 0",
            name=op.f("ck_speaker_turns_start_ms_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["speaker_id"],
            ["speakers.id"],
            name=op.f("fk_speaker_turns_speaker_id_speakers"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["transcript_id"],
            ["transcripts.id"],
            name=op.f("fk_speaker_turns_transcript_id_transcripts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_speaker_turns")),
    )
    op.create_index(
        op.f("ix_speaker_turns_speaker_id"),
        "speaker_turns",
        ["speaker_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_speaker_turns_transcript_id"),
        "speaker_turns",
        ["transcript_id"],
        unique=False,
    )
    op.create_table(
        "words",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("segment_id", sa.String(length=36), nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=False),
        sa.Column("end_ms", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "end_ms > start_ms",
            name=op.f("ck_words_offsets_increasing"),
        ),
        sa.CheckConstraint(
            "start_ms >= 0",
            name=op.f("ck_words_start_ms_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["segments.id"],
            name=op.f("fk_words_segment_id_segments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_words")),
    )
    op.create_index(
        op.f("ix_words_segment_id"),
        "words",
        ["segment_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the initial schema in reverse dependency order."""

    op.drop_index(op.f("ix_words_segment_id"), table_name="words")
    op.drop_table("words")
    op.drop_index(
        op.f("ix_speaker_turns_transcript_id"),
        table_name="speaker_turns",
    )
    op.drop_index(
        op.f("ix_speaker_turns_speaker_id"),
        table_name="speaker_turns",
    )
    op.drop_table("speaker_turns")
    op.drop_index(op.f("ix_segments_transcript_id"), table_name="segments")
    op.drop_table("segments")
    op.drop_index(
        op.f("ix_transcripts_project_id"),
        table_name="transcripts",
    )
    op.drop_index(
        op.f("ix_transcripts_media_asset_id"),
        table_name="transcripts",
    )
    op.drop_table("transcripts")
    op.drop_index(
        op.f("ix_transcription_jobs_state"),
        table_name="transcription_jobs",
    )
    op.drop_index(
        op.f("ix_transcription_jobs_project_id"),
        table_name="transcription_jobs",
    )
    op.drop_index(
        op.f("ix_transcription_jobs_media_asset_id"),
        table_name="transcription_jobs",
    )
    op.drop_table("transcription_jobs")
    op.drop_index(op.f("ix_speakers_project_id"), table_name="speakers")
    op.drop_table("speakers")
    op.drop_index(
        op.f("ix_media_assets_project_id"),
        table_name="media_assets",
    )
    op.drop_index(
        op.f("ix_media_assets_content_sha256"),
        table_name="media_assets",
    )
    op.drop_table("media_assets")
    op.drop_table("projects")
