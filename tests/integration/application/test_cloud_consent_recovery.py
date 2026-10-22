"""A restart never re-sends a cloud job: consent lasts for one run (ADR-0006)."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportMissingImports=false

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import test_job_runner as tjr
import test_synthesis_runner as tsr

from voz.application.ports.speech_synthesis import (
    SynthesisLocality,
    SynthesisProviderInfo,
)
from voz.application.ports.transcription_job_selection import JobSelection
from voz.application.synthesis.runner import SynthesisRunner
from voz.application.synthesis_provider_registry import SynthesisProviderRegistry
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.synthesis_job import SynthesisJob, SynthesisJobState
from voz.domain.entities.synthesis_request import SynthesisRequest
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.infrastructure.persistence.synthesis import (
    SqliteSynthesisJobRepository,
    SqliteSynthesizedAudioRepository,
)
from voz.infrastructure.persistence.transcription_job_selections import (
    SqliteTranscriptionJobSelectionRepository,
)

EXPIRED = "cloud_consent_expired"


def test_recover_fails_cloud_transcription_without_calling_the_provider(
    tmp_path: Path,
) -> None:
    fixture = tjr.harness(tmp_path)
    cloud = fixture.job
    local = TranscriptionJob.create(
        job_id=uuid4(),
        project_id=cloud.project_id,
        media_asset_id=cloud.media_asset_id,
        now=tjr.BASE_TIME + timedelta(seconds=1),
    )
    fixture.jobs.add(local)
    SqliteTranscriptionJobSelectionRepository(fixture.engine).add(
        JobSelection(
            job_id=local.id,
            option_id="option-v1-local",
            model=ModelDescriptor(
                provider_id="fake-local",
                model_id="fixture",
                display_name="Local",
                capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
            ),
            execution=None,
            language=None,
            created_at=tjr.BASE_TIME,
        )
    )
    runner = replace(fixture.runner, cloud_provider_ids=frozenset({"fake-asr"}))

    assert runner.recover() == (local.id,)

    failed = fixture.persisted()
    assert failed.state is TranscriptionJobState.FAILED
    assert failed.error_code == EXPIRED
    assert runner.run_job(cloud.id) == failed
    assert fixture.provider.calls == 0
    fixture.engine.dispose()


class _TtsAs(tsr.ScriptedTts):
    """The scripted engine declaring another id and locality."""

    def __init__(self, provider_id: str, locality: SynthesisLocality) -> None:
        super().__init__()
        self._declared = SynthesisProviderInfo(
            provider_id=provider_id,
            display_name=provider_id,
            locality=locality,
            max_chunk_chars=tsr.MAX_CHARS,
        )

    def describe(self) -> SynthesisProviderInfo:
        return self._declared


def test_recover_fails_cloud_synthesis_and_keeps_local_resumable(
    tmp_path: Path,
) -> None:
    fixture = tsr.harness(tmp_path)  # its job asks for provider "fake-tts"
    cloud_engine = _TtsAs("fake-tts", SynthesisLocality.CLOUD)
    local_engine = _TtsAs("fake-local", SynthesisLocality.LOCAL)
    local = SynthesisJob.create(
        job_id=uuid4(),
        request=SynthesisRequest(
            text=tsr.TEXT,
            provider_id="fake-local",
            model_id="tone",
            voice_id="tone-low",
        ),
        chunks_total=len(tsr.CHUNKS),
        now=tsr.BASE + timedelta(seconds=1),
    )
    fixture.jobs.add(local)
    ticks = iter(range(1, 10_000))
    runner = SynthesisRunner(
        jobs=fixture.jobs,
        audio=SqliteSynthesizedAudioRepository(fixture.engine),
        storage=fixture.storage,
        providers=SynthesisProviderRegistry([cloud_engine, local_engine]),
        catalog=tsr.Catalog(),
        clock=lambda: tsr.BASE + timedelta(seconds=next(ticks)),
    )

    assert runner.recover() == (local.id,)

    failed = fixture.persisted()
    assert failed.state is SynthesisJobState.FAILED
    assert failed.error_code == EXPIRED
    kept = SqliteSynthesisJobRepository(fixture.engine).get(local.id)
    assert kept is not None and kept.state is SynthesisJobState.QUEUED
    assert runner.run_job(fixture.job.id) == failed
    assert cloud_engine.calls == 0
    fixture.engine.dispose()
