"""SQLAlchemy Core schema for VOZ persistence adapters."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    false,
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
    Column(
        "speaker_id",
        String(36),
        ForeignKey("speakers.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("edited", Boolean, nullable=False, server_default=false()),
    Column("revision", Integer, nullable=False, server_default="0"),
    Column("original_text", Text, nullable=True),
    # JSON {"flags": [...], "avg_logprob": x}; NULL when nothing was flagged.
    Column("quality_json", Text, nullable=True),
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

transcription_job_selections = Table(
    "transcription_job_selections",
    metadata,
    Column(
        "job_id",
        String(36),
        ForeignKey("transcription_jobs.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("option_id", Text, nullable=False),
    Column("provider_id", Text, nullable=False),
    Column("model_id", Text, nullable=False),
    Column("source", Text, nullable=True),
    Column("revision", Text, nullable=True),
    Column("language", Text, nullable=True),
    Column("model_json", Text, nullable=False),
    Column("execution_json", Text, nullable=True),
    Column("created_at", String(40), nullable=False),
    Column("diarization_json", Text, nullable=True),
    Column("diarization_error_code", Text, nullable=True),
    # Full QualityProfile JSON and the frozen glossary list (S13.01/S13.02);
    # NULL for jobs created before profiles existed.
    Column("profile_json", Text, nullable=True),
    Column("glossary_json", Text, nullable=True),
)

project_glossaries = Table(
    "project_glossaries",
    metadata,
    Column(
        "project_id",
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("terms_json", Text, nullable=False),
    Column("updated_at", String(40), nullable=False),
)

__all__ = [
    "media_assets",
    "metadata",
    "project_glossaries",
    "projects",
    "segments",
    "speaker_turns",
    "speakers",
    "transcription_checkpoints",
    "transcription_job_selections",
    "transcription_jobs",
    "transcripts",
    "words",
]
