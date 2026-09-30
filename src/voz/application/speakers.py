"""Use cases to list, restyle, merge and manually assign transcript speakers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

from voz.application.assign_speakers import TranscriptNotFound
from voz.application.edit_segment import SegmentNotFound
from voz.application.ports.repositories import (
    SegmentRepository,
    SpeakerRepository,
    TranscriptRepository,
)
from voz.domain.entities.segment import Segment
from voz.domain.entities.speaker import Speaker

NAME_MAX_LENGTH = 80


class SpeakerNotFound(LookupError):
    """The speaker does not exist."""


class SpeakerUpdateInvalid(ValueError):
    """The requested name or color is not acceptable."""


class SpeakerMergeInvalid(ValueError):
    """The merge would cross transcripts or merge a speaker into itself."""


class SegmentSpeakerInvalid(ValueError):
    """The speaker does not belong to the segment's transcript."""


@dataclass(frozen=True, slots=True)
class SpeakerSummary:
    speaker: Speaker
    segment_count: int


def _count(
    segments: SegmentRepository, speakers: SpeakerRepository, speaker: Speaker
) -> SpeakerSummary:
    return SpeakerSummary(
        speaker,
        sum(
            1
            for transcript_id in speakers.transcript_ids(speaker.id)
            for segment in segments.list_by_transcript(transcript_id)
            if segment.speaker_id == speaker.id
        ),
    )


@dataclass(frozen=True, slots=True)
class ListTranscriptSpeakers:
    transcripts: TranscriptRepository
    segments: SegmentRepository
    speakers: SpeakerRepository

    def execute(self, transcript_id: UUID) -> list[SpeakerSummary]:
        if self.transcripts.get(transcript_id) is None:
            raise TranscriptNotFound(str(transcript_id))
        counts: dict[UUID, int] = {}
        for segment in self.segments.list_by_transcript(transcript_id):
            if segment.speaker_id is not None:
                counts[segment.speaker_id] = counts.get(segment.speaker_id, 0) + 1
        return [
            SpeakerSummary(speaker, counts.get(speaker.id, 0))
            for speaker in self.speakers.list_by_transcript(transcript_id)
        ]


@dataclass(frozen=True, slots=True)
class UpdateSpeaker:
    """Rename and/or recolor a speaker; no model is re-run (S6.09, S6.10)."""

    segments: SegmentRepository
    speakers: SpeakerRepository

    def execute(
        self, speaker_id: UUID, *, name: str | None = None, color: str | None = None
    ) -> SpeakerSummary:
        speaker = self.speakers.get(speaker_id)
        if speaker is None:
            raise SpeakerNotFound(str(speaker_id))
        if name is None and color is None:
            raise SpeakerUpdateInvalid("nothing to update")
        updated = speaker
        try:
            if name is not None:
                name = name.strip()
                if not 1 <= len(name) <= NAME_MAX_LENGTH:
                    raise ValueError("name length out of range")
                updated = replace(updated, name=name)
            if color is not None:
                updated = replace(updated, color=color)
            # replace() re-runs __post_init__, which validates name and color.
            updated = replace(
                updated, updated_at=max(datetime.now(UTC), speaker.updated_at)
            )
        except (TypeError, ValueError) as error:
            raise SpeakerUpdateInvalid(str(error)) from None
        self.speakers.save(updated)
        return _count(self.segments, self.speakers, updated)


@dataclass(frozen=True, slots=True)
class MergeSpeakers:
    """Fold ``source`` into ``target`` inside one transcript (S6.11)."""

    segments: SegmentRepository
    speakers: SpeakerRepository

    def execute(self, source_id: UUID, target_id: UUID) -> SpeakerSummary:
        source = self.speakers.get(source_id)
        if source is None:
            raise SpeakerNotFound(str(source_id))
        if source_id == target_id:
            raise SpeakerMergeInvalid("cannot merge a speaker into itself")
        target = self.speakers.get(target_id)
        if target is None:
            raise SpeakerMergeInvalid("target speaker does not exist")
        if not self.speakers.transcript_ids(source_id) & self.speakers.transcript_ids(
            target_id
        ):
            raise SpeakerMergeInvalid("speakers do not share a transcript")
        self.speakers.merge(source_id, target_id)
        return _count(self.segments, self.speakers, target)


@dataclass(frozen=True, slots=True)
class AssignSegmentSpeaker:
    """Manually (re)assign one segment's speaker without touching text (S6.12)."""

    segments: SegmentRepository
    speakers: SpeakerRepository

    def execute(self, segment_id: UUID, speaker_id: UUID | None) -> Segment:
        segment = self.segments.get(segment_id)
        if segment is None:
            raise SegmentNotFound(str(segment_id))
        if speaker_id is not None:
            if self.speakers.get(speaker_id) is None:
                raise SegmentSpeakerInvalid("speaker does not exist")
            if segment.transcript_id not in self.speakers.transcript_ids(speaker_id):
                raise SegmentSpeakerInvalid("speaker belongs to another transcript")
        self.segments.update_speakers({segment_id: speaker_id})
        return replace(segment, speaker_id=speaker_id)


__all__ = [
    "AssignSegmentSpeaker",
    "ListTranscriptSpeakers",
    "MergeSpeakers",
    "SegmentSpeakerInvalid",
    "SpeakerMergeInvalid",
    "SpeakerNotFound",
    "SpeakerSummary",
    "SpeakerUpdateInvalid",
    "UpdateSpeaker",
]
