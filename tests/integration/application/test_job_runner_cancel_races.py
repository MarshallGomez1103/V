"""Cancel wins over the worker's late writes (V0-09a, real SQLite).

Interleavings are forced without sleeps: the runner's injected ``clock`` is
called outside the runner lock right before each job write, so a clock hook that
calls ``runner.cancel`` is "the user clicks cancel while the worker is between
its cancel check and its write". Once CANCELLING is persisted (what the API
returned), the only state that may follow it is CANCELLED.
"""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportMissingImports=false

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import test_job_runner_diarization as diar
from sqlalchemy import Engine

from voz.application.job_runner import JobRunner, transcript_id_for
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
)
from voz.domain.entities.transcription_job import (
    TranscriptionJobState as S,
)
from voz.infrastructure.persistence.repositories import (
    SqliteTranscriptionJobRepository,
    SqliteTranscriptRepository,
)


class RecordingJobs(SqliteTranscriptionJobRepository):
    """Every state written through the jobs repository, in order."""

    def __init__(self, engine: Engine) -> None:
        super().__init__(engine)
        self.history: list[S] = []

    def save(self, job: TranscriptionJob) -> None:
        super().save(job)
        self.history.append(job.state)


def hook_clock(
    runner: JobRunner,
    fire_when: Callable[[], bool],
    action: Callable[[], TranscriptionJob],
) -> list[TranscriptionJob]:
    """Wrap the runner clock: run ``action`` once, the first time ``fire_when``."""
    base = runner.clock
    armed = [True]
    fired: list[TranscriptionJob] = []

    def clock() -> datetime:
        if armed[0] and fire_when():
            armed[0] = False
            fired.append(action())
        return base()

    runner.clock = clock
    return fired


def after_cancelling(states: list[S]) -> list[S]:
    return states[states.index(S.CANCELLING) + 1 :]


def test_cancel_during_persisting_ends_cancelled_keeping_text(tmp_path: Path) -> None:
    fx = diar.world(tmp_path, diarization=None)
    jobs = RecordingJobs(fx.engine)
    runner = fx.runner(None, jobs=jobs)
    fired = hook_clock(
        runner,
        lambda: fx.persisted().state is S.PERSISTING,
        lambda: runner.cancel(fx.job.id),
    )

    finished = runner.run_job(fx.job.id)

    assert fired and fired[0].state is S.CANCELLING  # what POST /cancel returned
    assert finished is not None and finished.state is S.CANCELLED
    assert fx.persisted().state is S.CANCELLED
    assert after_cancelling(jobs.history) == [S.CANCELLED]
    transcripts = SqliteTranscriptRepository(fx.engine)
    assert transcripts.get(transcript_id_for(fx.job.id)) is not None
    fx.engine.dispose()


def test_late_progress_save_does_not_regress_cancelling(tmp_path: Path) -> None:
    fx = diar.world(tmp_path)
    jobs = RecordingJobs(fx.engine)
    runner = fx.runner(diar.FakeDiarizer(fx.timeline, fractions=(0.3,)), jobs=jobs)
    hook_clock(
        runner,
        lambda: "diarize" in fx.timeline.events,
        lambda: runner.cancel(fx.job.id),
    )

    finished = runner.run_job(fx.job.id)

    assert finished is not None and finished.state is S.CANCELLED
    assert after_cancelling(jobs.history) == [S.CANCELLED]
    fx.engine.dispose()


def test_last_checkpoint_commit_does_not_regress_cancelling(tmp_path: Path) -> None:
    fx = diar.world(tmp_path, diarization=None)
    runner = fx.runner(None)
    seen: list[S] = []
    base = runner.clock

    def sampling_clock() -> datetime:
        state = fx.persisted().state
        if not seen or seen[-1] is not state:
            seen.append(state)
        return base()

    runner.clock = sampling_clock
    hook_clock(
        runner,
        lambda: (
            fx.persisted().state is S.TRANSCRIBING
            and fx.timeline.events.count("asr.transcribe") == 3
        ),
        lambda: runner.cancel(fx.job.id),
    )

    finished = runner.run_job(fx.job.id)

    assert finished is not None and finished.state is S.CANCELLED
    assert set(after_cancelling(seen)) <= {S.CANCELLED}
    # The last chunk's checkpoint is still kept with the cancelled job.
    assert len(runner.checkpoints.list_for_job(fx.job.id)) == 3
    fx.engine.dispose()


def test_cancel_during_aligning_keeps_text_by_design(tmp_path: Path) -> None:
    """CANCELLED with a persisted transcript is the documented contract."""
    fx = diar.world(tmp_path, diarization=None)
    jobs = RecordingJobs(fx.engine)
    runner = fx.runner(None, jobs=jobs)
    hook_clock(
        runner,
        lambda: fx.persisted().state is S.ALIGNING,
        lambda: runner.cancel(fx.job.id),
    )

    finished = runner.run_job(fx.job.id)

    assert finished is not None and finished.state is S.CANCELLED
    assert after_cancelling(jobs.history) == [S.CANCELLED]
    transcripts = SqliteTranscriptRepository(fx.engine)
    assert transcripts.get(transcript_id_for(fx.job.id)) is not None
    fx.engine.dispose()
