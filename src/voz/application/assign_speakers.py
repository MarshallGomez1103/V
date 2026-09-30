"""Use case: persist a diarization result as speakers, turns and assignments."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from voz.application.diarization_reconcile import (
    DEFAULT_MIN_OVERLAP_RATIO,
    reconcile_turns,
)
from voz.application.ports.diarization import DiarizationResult
from voz.application.ports.repositories import (
    SegmentRepository,
    SpeakerRepository,
    SpeakerTurnRepository,
    TranscriptRepository,
)
from voz.domain.entities.speaker import Speaker, speaker_palette_color
from voz.domain.entities.speaker_turn import SpeakerTurn


class TranscriptNotFound(LookupError):
    """The transcript to diarize does not exist."""


@dataclass(frozen=True, slots=True)
class AssignSpeakersOutcome:
    speakers: tuple[Speaker, ...]
    """Speakers of the transcript's clusters, in first-appearance order."""
    turns: tuple[SpeakerTurn, ...]
    assigned_segments: int
    unassigned_segments: int


@dataclass(frozen=True, slots=True)
class AssignSpeakers:
    """Map provider clusters to ``Speaker`` identities and label segments.

    Idempotent: the cluster -> speaker mapping of the transcript is recovered
    from its stored turns, so re-running keeps existing speakers (with their
    renames and colors) instead of duplicating them, then replaces the turns
    and segment assignments.

    # ponytail: repos separados sin transacción común; un fallo entre pasos deja
    # speakers sin turns, y re-ejecutar los recrearía. Unificar si duele.
    """

    transcripts: TranscriptRepository
    segments: SegmentRepository
    speakers: SpeakerRepository
    speaker_turns: SpeakerTurnRepository
    min_overlap_ratio: float = DEFAULT_MIN_OVERLAP_RATIO

    def execute(
        self, transcript_id: UUID, result: DiarizationResult
    ) -> AssignSpeakersOutcome:
        transcript = self.transcripts.get(transcript_id)
        if transcript is None:
            raise TranscriptNotFound(str(transcript_id))

        segments = self.segments.list_by_transcript(transcript_id)
        reconciliation = reconcile_turns(
            segments, result.turns, min_overlap_ratio=self.min_overlap_ratio
        )

        known = {s.id: s for s in self.speakers.list_by_project(transcript.project_id)}
        speaker_by_cluster: dict[str, Speaker] = {}
        for turn in self.speaker_turns.list_by_transcript(transcript_id):
            if turn.speaker_id is not None and turn.speaker_id in known:
                speaker_by_cluster.setdefault(
                    turn.cluster_label, known[turn.speaker_id]
                )

        ordered: list[Speaker] = []
        for index, cluster in enumerate(reconciliation.cluster_order):
            speaker = speaker_by_cluster.get(cluster)
            if speaker is None:
                speaker = Speaker(
                    transcript.project_id,
                    f"Speaker {index + 1}",
                    speaker_palette_color(index),
                )
                self.speakers.add(speaker)
                speaker_by_cluster[cluster] = speaker
            ordered.append(speaker)

        turns = tuple(
            SpeakerTurn(
                transcript_id,
                turn.cluster,
                turn.start_ms,
                turn.end_ms,
                speaker_id=speaker_by_cluster[turn.cluster].id,
            )
            for turn in sorted(result.turns, key=lambda t: (t.start_ms, t.end_ms))
        )
        self.speaker_turns.replace_for_transcript(transcript_id, turns)

        segment_speakers = {
            segment_id: None if cluster is None else speaker_by_cluster[cluster].id
            for segment_id, cluster in reconciliation.assignments.items()
        }
        self.segments.update_speakers(segment_speakers)

        assigned = sum(1 for speaker_id in segment_speakers.values() if speaker_id)
        return AssignSpeakersOutcome(
            tuple(ordered), turns, assigned, len(segment_speakers) - assigned
        )


__all__ = ["AssignSpeakers", "AssignSpeakersOutcome", "TranscriptNotFound"]
