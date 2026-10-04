"""Persistence contracts expressed only in domain terms.

These synchronous ports define the initial local persistence boundary. Adapters
may use SQLite or another storage mechanism, but callers only exchange complete
domain entities and UUID identities.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID

from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.project import Project
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker
from voz.domain.entities.speaker_turn import SpeakerTurn
from voz.domain.entities.transcript import Transcript
from voz.domain.entities.transcription_job import TranscriptionJob
from voz.domain.entities.word import Word


@runtime_checkable
class ProjectRepository(Protocol):
    """Persist and recover top-level project aggregates."""

    def add(self, project: Project) -> None:
        """Persist a new project."""
        ...

    def save(self, project: Project) -> None:
        """Persist the current snapshot of an existing project."""
        ...

    def get(self, project_id: UUID) -> Project | None:
        """Return a project by identity, or ``None`` when absent."""
        ...

    def list_all(self) -> Sequence[Project]:
        """Return every project in a stable adapter-defined order."""
        ...


@runtime_checkable
class MediaAssetRepository(Protocol):
    """Persist media metadata without exposing storage locations."""

    def add(self, media_asset: MediaAsset) -> None:
        """Persist a new media asset."""
        ...

    def save(self, media_asset: MediaAsset) -> None:
        """Persist the current snapshot of an existing media asset."""
        ...

    def get(self, media_asset_id: UUID) -> MediaAsset | None:
        """Return a media asset by identity, or ``None`` when absent."""
        ...

    def list_by_project(self, project_id: UUID) -> Sequence[MediaAsset]:
        """Return media assets owned by a project."""
        ...


@runtime_checkable
class TranscriptRepository(Protocol):
    """Persist transcript roots independently from their timed children."""

    def add(self, transcript: Transcript) -> None:
        """Persist a new transcript."""
        ...

    def save(self, transcript: Transcript) -> None:
        """Persist the current snapshot of an existing transcript."""
        ...

    def get(self, transcript_id: UUID) -> Transcript | None:
        """Return a transcript by identity, or ``None`` when absent."""
        ...

    def list_by_project(self, project_id: UUID) -> Sequence[Transcript]:
        """Return transcripts owned by a project."""
        ...

    def list_by_media_asset(self, media_asset_id: UUID) -> Sequence[Transcript]:
        """Return transcript versions associated with one media asset."""
        ...


@runtime_checkable
class SegmentRepository(Protocol):
    """Persist transcript segments and recover them in timeline order."""

    def add(self, segment: Segment) -> None:
        """Persist a new segment."""
        ...

    def save(self, segment: Segment) -> None:
        """Persist the current snapshot of an existing segment."""
        ...

    def update_text_if_revision(self, segment: Segment, expected_revision: int) -> bool:
        """Atomically store an edited text if the stored revision still matches.

        Returns ``False`` (nothing written) when the segment is missing or its
        stored revision differs from ``expected_revision``.
        """
        ...

    def update_speakers(self, assignments: Mapping[UUID, UUID | None]) -> None:
        """Set only ``speaker_id`` of the given segments in one transaction.

        Text, words and revisions are untouched; unknown segment ids are ignored.
        """
        ...

    def get(self, segment_id: UUID) -> Segment | None:
        """Return a segment by identity, or ``None`` when absent."""
        ...

    def list_by_transcript(self, transcript_id: UUID) -> Sequence[Segment]:
        """Return a transcript's segments in timeline order."""
        ...


@runtime_checkable
class WordRepository(Protocol):
    """Persist word timings independently from segment snapshots."""

    def add(self, word: Word) -> None:
        """Persist a new timed word."""
        ...

    def save(self, word: Word) -> None:
        """Persist the current snapshot of an existing word."""
        ...

    def get(self, word_id: UUID) -> Word | None:
        """Return a word by identity, or ``None`` when absent."""
        ...

    def list_by_segment(self, segment_id: UUID) -> Sequence[Word]:
        """Return a segment's words in timeline order."""
        ...


@runtime_checkable
class SpeakerRepository(Protocol):
    """Persist editable speaker identities within a project."""

    def add(self, speaker: Speaker) -> None:
        """Persist a new speaker."""
        ...

    def save(self, speaker: Speaker) -> None:
        """Persist the current snapshot of an existing speaker."""
        ...

    def get(self, speaker_id: UUID) -> Speaker | None:
        """Return a speaker by identity, or ``None`` when absent."""
        ...

    def list_by_project(self, project_id: UUID) -> Sequence[Speaker]:
        """Return speakers owned by a project."""
        ...

    def list_by_transcript(self, transcript_id: UUID) -> Sequence[Speaker]:
        """Return speakers referenced by a transcript's segments or turns."""
        ...

    def transcript_ids(self, speaker_id: UUID) -> frozenset[UUID]:
        """Return transcripts whose segments or turns reference the speaker."""
        ...

    def delete_unreferenced(self, speaker_ids: Collection[UUID]) -> None:
        """Delete those speakers that no segment or turn references any more."""
        ...

    def merge(self, source_id: UUID, target_id: UUID) -> None:
        """Move segments and turns of ``source_id`` to ``target_id``, then delete it.

        One transaction: either everything moves and the source disappears, or
        nothing changes.
        """
        ...


@runtime_checkable
class SpeakerTurnRepository(Protocol):
    """Persist timeline assignments separately from speaker identity."""

    def add(self, speaker_turn: SpeakerTurn) -> None:
        """Persist a new speaker turn."""
        ...

    def save(self, speaker_turn: SpeakerTurn) -> None:
        """Persist the current snapshot of an existing speaker turn."""
        ...

    def replace_for_transcript(
        self,
        transcript_id: UUID,
        turns: Sequence[SpeakerTurn],
    ) -> None:
        """Atomically swap every turn of a transcript for the given ones."""
        ...

    def get(self, speaker_turn_id: UUID) -> SpeakerTurn | None:
        """Return a speaker turn by identity, or ``None`` when absent."""
        ...

    def list_by_transcript(self, transcript_id: UUID) -> Sequence[SpeakerTurn]:
        """Return a transcript's speaker turns in timeline order."""
        ...

    def list_by_speaker(self, speaker_id: UUID) -> Sequence[SpeakerTurn]:
        """Return every turn currently assigned to a speaker."""
        ...


@runtime_checkable
class TranscriptionJobRepository(Protocol):
    """Persist job snapshots required for restart recovery."""

    def add(self, job: TranscriptionJob) -> None:
        """Persist a new transcription job."""
        ...

    def save(self, job: TranscriptionJob) -> None:
        """Persist the current snapshot of an existing job."""
        ...

    def get(self, job_id: UUID) -> TranscriptionJob | None:
        """Return a job by identity, or ``None`` when absent."""
        ...

    def list_by_project(self, project_id: UUID) -> Sequence[TranscriptionJob]:
        """Return jobs owned by a project."""
        ...

    def list_by_media_asset(
        self,
        media_asset_id: UUID,
    ) -> Sequence[TranscriptionJob]:
        """Return jobs associated with a media asset."""
        ...

    def list_recoverable(self) -> Sequence[TranscriptionJob]:
        """Return non-terminal jobs that require restart recovery."""
        ...


__all__ = [
    "MediaAssetRepository",
    "ProjectRepository",
    "SegmentRepository",
    "SpeakerRepository",
    "SpeakerTurnRepository",
    "TranscriptRepository",
    "TranscriptionJobRepository",
    "WordRepository",
]
