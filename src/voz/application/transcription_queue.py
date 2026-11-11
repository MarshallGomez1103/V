"""Transcribe a whole project: one ordinary job per eligible recording.

The queue is not a second state machine. It creates every job at once, in import
order and in one transaction, and the single global worker runs them one after
another; the queue and its items are read off the jobs.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from voz.application.create_transcription_job import CreateTranscriptionJob
from voz.application.job_runner import JobNotFound, JobTerminal, transcript_id_for
from voz.application.job_status import TranscriptLookup, job_has_transcript
from voz.application.ports.diarization import DiarizationOptions
from voz.application.ports.repositories import (
    MediaAssetRepository,
    ProjectRepository,
    TranscriptionJobRepository,
)
from voz.application.ports.transcription_queue import (
    JobCanceller,
    TranscriptionQueueRepository,
)
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.domain.entities.transcription_queue import (
    QueueItemStatus,
    QueueState,
    SkippedRecording,
    SkipReason,
    TranscriptionQueue,
    queue_item_status,
    queue_state,
)


class QueueFailureCode(StrEnum):
    """Stable codes of the queue itself; job validation keeps its own codes."""

    ACTIVE = "transcription_queue_active"
    EMPTY = "transcription_queue_empty"
    CLOUD_UNSUPPORTED = "transcription_queue_cloud_unsupported"
    NOT_FOUND = "transcription_queue_not_found"
    FINISHED = "transcription_queue_finished"
    PROJECT_NOT_FOUND = "project_not_found"


@dataclass(frozen=True, slots=True)
class SkippedItem:
    """A recording that did not enter the queue, named for the person."""

    media_asset_id: UUID
    filename: str
    reason: SkipReason


class QueueError(RuntimeError):
    """Typed queue failure with a user-safe message."""

    def __init__(
        self,
        code: QueueFailureCode,
        user_message: str,
        *,
        skipped: tuple[SkippedItem, ...] = (),
    ) -> None:
        self.code = code
        self.user_message = user_message
        self.skipped = skipped
        super().__init__(user_message)


@dataclass(frozen=True, slots=True)
class CreatedQueue:
    queue_id: UUID
    job_ids: tuple[UUID, ...]
    """In position order: enqueue them in this order."""


@dataclass(frozen=True, slots=True)
class QueueItemView:
    position: int
    media_asset_id: UUID
    filename: str
    job: TranscriptionJob
    status: QueueItemStatus
    transcript_id: UUID | None


@dataclass(frozen=True, slots=True)
class QueueCounts:
    total: int
    pending: int
    running: int
    done: int
    error: int
    cancelled: int
    skipped: int


@dataclass(frozen=True, slots=True)
class QueueSnapshot:
    queue: TranscriptionQueue
    items: tuple[QueueItemView, ...]
    skipped: tuple[SkippedItem, ...]

    @property
    def state(self) -> QueueState:
        return queue_state(item.status for item in self.items)

    @property
    def counts(self) -> QueueCounts:
        def of(status: QueueItemStatus) -> int:
            return sum(1 for item in self.items if item.status is status)

        return QueueCounts(
            total=len(self.items),
            pending=of(QueueItemStatus.PENDING),
            running=of(QueueItemStatus.RUNNING),
            done=of(QueueItemStatus.DONE),
            error=of(QueueItemStatus.ERROR),
            cancelled=of(QueueItemStatus.CANCELLED),
            skipped=len(self.skipped),
        )

    @property
    def progress(self) -> float:
        """Finished items count fully; running ones by their own progress."""
        if not self.items:
            return 1.0
        total = 0.0
        for item in self.items:
            if item.status is QueueItemStatus.RUNNING:
                total += item.job.progress
            elif item.status is not QueueItemStatus.PENDING:
                total += 1.0
        return total / len(self.items)


def _jobs_of(
    queues: TranscriptionQueueRepository,
    jobs: TranscriptionJobRepository,
    queue_id: UUID,
) -> list[TranscriptionJob]:
    # ponytail: one read per item; ceiling: a SQL read model next to library.py.
    found = (jobs.get(job_id) for job_id in queues.job_ids(queue_id))
    return [job for job in found if job is not None]


def _skip_reason(
    asset: MediaAsset, history: Sequence[TranscriptionJob]
) -> SkipReason | None:
    """Transcribed, then active, then unmeasured; failed or cancelled do not count."""
    if any(job.state is TranscriptionJobState.COMPLETED for job in history):
        return SkipReason.ALREADY_TRANSCRIBED
    if any(not job.state.is_terminal for job in history):
        return SkipReason.JOB_ACTIVE
    if asset.duration_ms is None:
        return SkipReason.DURATION_UNKNOWN
    return None


@dataclass(slots=True)
class CreateTranscriptionQueue:
    """Validate once, then create every job and the queue as one write."""

    create_job: CreateTranscriptionJob
    media_assets: MediaAssetRepository
    jobs: TranscriptionJobRepository
    queues: TranscriptionQueueRepository

    def execute(
        self,
        *,
        project_id: UUID,
        option_id: str,
        language: str | None = None,
        diarization: DiarizationOptions | None = None,
        profile: str | None = None,
        prompt: str | None = None,
    ) -> CreatedQueue:
        """Raises ``CreateJobError`` for the options and ``QueueError`` otherwise."""
        create = self.create_job
        # Same gate as job creation, so no job appears between the checks and the write.
        with create.admission.hold():
            create.require_project(project_id)
            # Consent covers one run and a queue cannot ask for it, so it is not
            # granted here: cloud options are refused right below.
            prepared = create.prepare(
                project_id=project_id,
                option_id=option_id,
                profile=profile,
                prompt=prompt,
                cloud_consent=True,
            )
            if prepared.option.cloud:
                raise QueueError(
                    QueueFailureCode.CLOUD_UNSUPPORTED,
                    "A project queue only runs on this machine; pick a local option.",
                )
            self._reject_unfinished_queue(project_id)
            eligible, skipped = self._split(project_id)
            if not eligible:
                raise QueueError(
                    QueueFailureCode.EMPTY,
                    "No recording of this project can be transcribed now.",
                    skipped=skipped,
                )
            create.check_resources(prepared.option, prepared.model, diarization)
            now = create.clock()
            created = [
                create.new_job(
                    prepared,
                    project_id=project_id,
                    media_asset_id=asset.id,
                    language=language,
                    diarization=diarization,
                    clip=None,
                    now=now,
                )
                for asset in eligible
            ]
            queue = TranscriptionQueue(
                create.id_factory(),
                project_id,
                now,
                tuple(SkippedRecording(s.media_asset_id, s.reason) for s in skipped),
            )
            self.queues.add(queue, [(item.job, item.selection) for item in created])
        return CreatedQueue(queue.id, tuple(item.job.id for item in created))

    def _reject_unfinished_queue(self, project_id: UUID) -> None:
        latest = self.queues.latest_for_project(project_id)
        if latest is None:
            return
        statuses = (
            queue_item_status(job.state)
            for job in _jobs_of(self.queues, self.jobs, latest.id)
        )
        if queue_state(statuses) is QueueState.RUNNING:
            raise QueueError(
                QueueFailureCode.ACTIVE,
                "This project already has a queue in progress.",
            )

    def _split(
        self, project_id: UUID
    ) -> tuple[list[MediaAsset], tuple[SkippedItem, ...]]:
        """Eligible recordings and the skipped ones, both in import order."""
        eligible: list[MediaAsset] = []
        skipped: list[SkippedItem] = []
        assets = sorted(
            self.media_assets.list_by_project(project_id),
            key=lambda asset: (asset.created_at, str(asset.id)),
        )
        for asset in assets:
            reason = _skip_reason(asset, self.jobs.list_by_media_asset(asset.id))
            if reason is None:
                eligible.append(asset)
            else:
                skipped.append(SkippedItem(asset.id, asset.display_name, reason))
        return eligible, tuple(skipped)


@dataclass(slots=True)
class GetTranscriptionQueue:
    projects: ProjectRepository
    queues: TranscriptionQueueRepository
    jobs: TranscriptionJobRepository
    media_assets: MediaAssetRepository
    transcripts: TranscriptLookup

    def for_project(self, project_id: UUID) -> QueueSnapshot | None:
        """The most recent queue of the project, or ``None`` when it never had one."""
        if self.projects.get(project_id) is None:
            raise QueueError(
                QueueFailureCode.PROJECT_NOT_FOUND, "The project does not exist."
            )
        queue = self.queues.latest_for_project(project_id)
        return None if queue is None else self._snapshot(queue)

    def by_id(self, queue_id: UUID) -> QueueSnapshot:
        queue = self.queues.get(queue_id)
        if queue is None:
            raise QueueError(
                QueueFailureCode.NOT_FOUND, "The transcription queue does not exist."
            )
        return self._snapshot(queue)

    def _snapshot(self, queue: TranscriptionQueue) -> QueueSnapshot:
        items = tuple(
            QueueItemView(
                position=position,
                media_asset_id=job.media_asset_id,
                filename=self._filename(job.media_asset_id),
                job=job,
                status=queue_item_status(job.state),
                transcript_id=(
                    transcript_id_for(job.id)
                    if job_has_transcript(job, self.transcripts)
                    else None
                ),
            )
            for position, job in enumerate(_jobs_of(self.queues, self.jobs, queue.id))
        )
        skipped = tuple(
            SkippedItem(s.media_asset_id, self._filename(s.media_asset_id), s.reason)
            for s in queue.skipped
        )
        return QueueSnapshot(queue, items, skipped)

    def _filename(self, media_asset_id: UUID) -> str:
        asset = self.media_assets.get(media_asset_id)
        return "" if asset is None else asset.display_name


@dataclass(slots=True)
class CancelTranscriptionQueue:
    queues: TranscriptionQueueRepository
    jobs: TranscriptionJobRepository
    canceller: JobCanceller

    def execute(self, queue_id: UUID) -> None:
        """Cancel the waiting items first, so the worker cannot pick the next one.

        Cancelling the running item first would let the worker start the following
        item before it is cancelled.
        """
        if self.queues.get(queue_id) is None:
            raise QueueError(
                QueueFailureCode.NOT_FOUND, "The transcription queue does not exist."
            )
        if queue_state(self._statuses(queue_id)) is QueueState.FINISHED:
            raise QueueError(
                QueueFailureCode.FINISHED, "The transcription queue already finished."
            )
        self._cancel_where(
            queue_id, lambda state: state is TranscriptionJobState.QUEUED
        )
        self._cancel_where(queue_id, lambda state: not state.is_terminal)

    def _statuses(self, queue_id: UUID) -> list[QueueItemStatus]:
        return [
            queue_item_status(job.state)
            for job in _jobs_of(self.queues, self.jobs, queue_id)
        ]

    def _cancel_where(
        self, queue_id: UUID, wanted: Callable[[TranscriptionJobState], bool]
    ) -> None:
        # Re-read each pass: an item may have started or finished since the last one.
        for job in _jobs_of(self.queues, self.jobs, queue_id):
            if not wanted(job.state):
                continue
            try:
                self.canceller.cancel(job.id)
            except (JobNotFound, JobTerminal):
                continue  # it finished between the read and the cancel


__all__ = [
    "CancelTranscriptionQueue",
    "CreateTranscriptionQueue",
    "CreatedQueue",
    "GetTranscriptionQueue",
    "QueueCounts",
    "QueueError",
    "QueueFailureCode",
    "QueueItemView",
    "QueueSnapshot",
    "SkippedItem",
]
