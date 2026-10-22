"""A cloud synthesis engine needs explicit consent per request (ADR-0006)."""

from __future__ import annotations

from typing import Any

import pytest
from synthesis_support import NOW, MemoryAudio, MemoryCatalog, MemoryJobs
from synthesis_support import installed_fake_model as installed_model

from voz.application.admission import AdmissionGate
from voz.application.ports.speech_synthesis import (
    SynthesisLocality,
    SynthesisProviderInfo,
    SynthesisRequirements,
)
from voz.application.synthesis import (
    CreateSynthesisJob,
    SynthesisJobError,
    SynthesisJobFailureCode,
)
from voz.application.synthesis_provider_registry import SynthesisProviderRegistry
from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.domain.entities.synthesis_job import SynthesisJobState
from voz.domain.entities.voice import Voice
from voz.infrastructure.tts.fake import (
    FAKE_TTS_PROVIDER_ID,
    FakeSpeechSynthesisProvider,
)

BASE: dict[str, Any] = {
    "text": "Hello there.",
    "provider_id": FAKE_TTS_PROVIDER_ID,
    "model_id": "tone",
    "voice_id": "tone-low",
}


class CountingCloudTts(FakeSpeechSynthesisProvider):
    """Fake engine that declares itself cloud and counts every adapter call."""

    def __init__(self) -> None:
        super().__init__(max_chunk_chars=40)
        self.calls = 0

    def describe(self) -> SynthesisProviderInfo:
        return SynthesisProviderInfo(
            provider_id=FAKE_TTS_PROVIDER_ID,
            display_name="Fake cloud TTS",
            locality=SynthesisLocality.CLOUD,
            max_chunk_chars=40,
        )

    def voices(self, model: ModelDescriptor) -> tuple[Voice, ...]:
        self.calls += 1
        return super().voices(model)

    def requirements(self, model: ModelDescriptor) -> SynthesisRequirements:
        self.calls += 1
        return super().requirements(model)


def _create(
    provider: FakeSpeechSynthesisProvider, jobs: MemoryJobs
) -> CreateSynthesisJob:
    return CreateSynthesisJob(
        providers=SynthesisProviderRegistry((provider,)),
        catalog=MemoryCatalog(installed_model()),
        jobs=jobs,
        audio=MemoryAudio(),
        clock=lambda: NOW,
        admission=AdmissionGate(),
    )


@pytest.mark.parametrize("flag", [{}, {"cloud_consent": False}])
def test_cloud_engine_without_consent_is_refused_before_any_call(
    flag: dict[str, Any],
) -> None:
    jobs, cloud = MemoryJobs(), CountingCloudTts()

    with pytest.raises(SynthesisJobError) as caught:
        _create(cloud, jobs).execute(**BASE, **flag)

    assert caught.value.code is SynthesisJobFailureCode.CLOUD_CONSENT_REQUIRED
    assert caught.value.code.value == "cloud_consent_required"
    assert jobs.items == {}
    assert cloud.calls == 0


def test_cloud_engine_with_consent_creates_the_job() -> None:
    jobs = MemoryJobs()

    created = _create(CountingCloudTts(), jobs).execute(**BASE, cloud_consent=True)

    assert created.job.state is SynthesisJobState.QUEUED
    assert jobs.get(created.job.id) == created.job


def test_local_engine_ignores_the_flag() -> None:
    jobs = MemoryJobs()
    local = FakeSpeechSynthesisProvider(max_chunk_chars=40)

    assert _create(local, jobs).execute(**BASE).job.state is SynthesisJobState.QUEUED
    assert len(jobs.items) == 1
