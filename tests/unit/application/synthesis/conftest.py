"""Fixtures: a ready fake engine and a use case wired to in-memory ports."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from uuid import uuid4

import pytest
from synthesis_support import (
    NOW,
    MemoryAudio,
    MemoryCatalog,
    MemoryJobs,
    installed_fake_model,
)

from voz.application.admission import AdmissionGate
from voz.application.ports.transcription_options import ModelRegistration
from voz.application.synthesis import CreateSynthesisJob
from voz.application.synthesis_provider_registry import SynthesisProviderRegistry
from voz.infrastructure.tts.fake import FakeSpeechSynthesisProvider


@pytest.fixture
def jobs() -> MemoryJobs:
    return MemoryJobs()


@pytest.fixture
def audio() -> MemoryAudio:
    return MemoryAudio()


@pytest.fixture
def registry() -> SynthesisProviderRegistry:
    return SynthesisProviderRegistry((FakeSpeechSynthesisProvider(max_chunk_chars=40),))


@pytest.fixture
def make_create(
    jobs: MemoryJobs, audio: MemoryAudio, registry: SynthesisProviderRegistry
) -> Callable[..., CreateSynthesisJob]:
    ticks = iter(range(10_000))

    def build(*registrations: ModelRegistration) -> CreateSynthesisJob:
        return CreateSynthesisJob(
            providers=registry,
            catalog=MemoryCatalog(*(registrations or (installed_fake_model(),))),
            jobs=jobs,
            audio=audio,
            id_factory=uuid4,
            clock=lambda: NOW + timedelta(seconds=next(ticks)),
            admission=AdmissionGate(),
        )

    return build


@pytest.fixture
def create(make_create: Callable[..., CreateSynthesisJob]) -> CreateSynthesisJob:
    return make_create()
