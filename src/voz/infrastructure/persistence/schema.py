"""SQLAlchemy Core schema for VOZ persistence adapters."""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)

projects = Table(
    "projects",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
)

media_assets = Table(
    "media_assets",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "project_id",
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("content_sha256", String(64), nullable=False, index=True),
    Column("display_name", Text, nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("media_type", Text, nullable=True),
    Column("duration_ms", BigInteger, nullable=True),
    Column("created_at", String(40), nullable=False),
    CheckConstraint("size_bytes > 0", name="size_bytes_positive"),
    CheckConstraint(
        "duration_ms IS NULL OR duration_ms > 0",
        name="duration_ms_positive",
    ),
)

transcripts = Table(
    "transcripts",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "project_id",
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column(
        "media_asset_id",
        String(36),
        ForeignKey("media_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("language", Text, nullable=True),
    Column("created_at", String(40), nullable=False),
)

segments = Table(
    "segments",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "transcript_id",
        String(36),
        ForeignKey("transcripts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("start_ms", BigInteger, nullable=False),
    Column("end_ms", BigInteger, nullable=False),
    Column("text", Text, nullable=False),
    CheckConstraint("start_ms >= 0", name="start_ms_non_negative"),
    CheckConstraint("end_ms > start_ms", name="offsets_increasing"),
)

words = Table(
    "words",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "segment_id",
        String(36),
        ForeignKey("segments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("start_ms", BigInteger, nullable=False),
    Column("end_ms", BigInteger, nullable=False),
    Column("text", Text, nullable=False),
    CheckConstraint("start_ms >= 0", name="start_ms_non_negative"),
    CheckConstraint("end_ms > start_ms", name="offsets_increasing"),
)

speakers = Table(
    "speakers",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "project_id",
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("name", Text, nullable=False),
    Column("color", String(7), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)

speaker_turns = Table(
    "speaker_turns",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "transcript_id",
        String(36),
        ForeignKey("transcripts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("cluster_label", Text, nullable=False),
    Column("start_ms", BigInteger, nullable=False),
    Column("end_ms", BigInteger, nullable=False),
    Column(
        "speaker_id",
        String(36),
        ForeignKey("speakers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    ),
    CheckConstraint("start_ms >= 0", name="start_ms_non_negative"),
    CheckConstraint("end_ms > start_ms", name="offsets_increasing"),
)

transcription_jobs = Table(
    "transcription_jobs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "project_id",
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column(
        "media_asset_id",
        String(36),
        ForeignKey("media_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("state", String(32), nullable=False, index=True),
    Column("progress", Float(), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Column("error_code", Text, nullable=True),
    CheckConstraint(
        "progress >= 0.0 AND progress <= 1.0",
        name="progress_bounded",
    ),
)

transcription_checkpoints = Table(
    "transcription_checkpoints",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "job_id",
        String(36),
        ForeignKey("transcription_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("chunk_index", BigInteger, nullable=False),
    Column("process_start_ms", BigInteger, nullable=False),
    Column("process_end_ms", BigInteger, nullable=False),
    Column("owned_start_ms", BigInteger, nullable=False),
    Column("owned_end_ms", BigInteger, nullable=False),
    Column("provider_id", Text, nullable=False),
    Column("model_id", Text, nullable=False),
    Column("model_source", Text, nullable=True),
    Column("model_revision", Text, nullable=True),
    Column("requested_language", Text, nullable=True),
    Column("segments_json", Text, nullable=False),
    Column("language", Text, nullable=True),
    Column("progress", Float(), nullable=False),
    Column("job_progress", Float(), nullable=False),
    Column("completed_at", String(40), nullable=False),
    CheckConstraint("chunk_index >= 0", name="chunk_index_non_negative"),
    CheckConstraint("process_start_ms >= 0", name="process_start_non_negative"),
    CheckConstraint(
        "process_start_ms <= owned_start_ms",
        name="process_contains_owned_start",
    ),
    CheckConstraint("owned_start_ms < owned_end_ms", name="owned_offsets_increasing"),
    CheckConstraint(
        "owned_end_ms <= process_end_ms",
        name="process_contains_owned_end",
    ),
    CheckConstraint("progress > 0.0 AND progress <= 1.0", name="progress_bounded"),
    CheckConstraint(
        "job_progress > 0.0 AND job_progress <= 1.0",
        name="job_progress_bounded",
    ),
    UniqueConstraint("job_id", "chunk_index", name="uq_checkpoint_job_chunk"),
)

__all__ = [
    "media_assets",
    "metadata",
    "projects",
    "segments",
    "speaker_turns",
    "speakers",
    "transcription_checkpoints",
    "transcription_jobs",
    "transcripts",
    "words",
]
