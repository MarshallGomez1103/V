"""Use case: persist a diarization result as speakers, turns and assignments."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID, uuid5

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


@dataclass(frozen=True, slots=True)
class AssignProviderSpeakers:
    """Turn the opaque ``speaker`` labels of a cloud ASR into ``Speaker`` entities.

    Used only when no local diarization was requested (local wins). Speaker ids
    derive from the transcript and the label, so resuming a job reuses the same
    rows (keeping renames) instead of duplicating them. Names are "Hablante N"
    in order of first appearance; colors follow the same fixed palette.

    # ponytail: no hay turns (el proveedor no da tiempos de turno); una etiqueta
    # que el proveedor reutilice entre chunks para personas distintas se fusiona.
    """

    speakers: SpeakerRepository
    segments: SegmentRepository

    def execute(
        self,
        transcript_id: UUID,
        project_id: UUID,
        labels: Mapping[UUID, str],
    ) -> tuple[Speaker, ...]:
        """``labels`` maps segment id -> provider label, in timeline order."""
        by_label: dict[str, Speaker] = {}
        for label in labels.values():
            if label in by_label:
                continue
            speaker_id = uuid5(transcript_id, f"speaker:{label}")
            index = len(by_label)
            speaker = self.speakers.get(speaker_id)
            if speaker is None:
                speaker = Speaker(
                    project_id,
                    f"Hablante {index + 1}",
                    speaker_palette_color(index),
                    id=speaker_id,
                )
                self.speakers.add(speaker)
            by_label[label] = speaker
        self.segments.update_speakers(
            {segment_id: by_label[label].id for segment_id, label in labels.items()}
        )
        return tuple(by_label.values())


__all__ = [
    "AssignProviderSpeakers",
    "AssignSpeakers",
    "AssignSpeakersOutcome",
    "TranscriptNotFound",
]
