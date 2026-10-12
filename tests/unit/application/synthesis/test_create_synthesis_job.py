"""CreateSynthesisJob validates, chunks, persists and reuses identical results."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest
from synthesis_support import MemoryAudio, MemoryJobs

from voz.application.ports.transcription_options import (
    InstallationStatus,
    ModelRegistration,
)
from voz.application.synthesis import (
    CreatedSynthesis,
    CreateSynthesisJob,
    SynthesisJobError,
    SynthesisJobFailureCode,
    request_hash,
)
from voz.domain.entities.model_descriptor import ModelCapability
from voz.domain.entities.synthesis_job import SynthesisJobState
from voz.domain.entities.synthesized_audio import SynthesizedAudio
from voz.infrastructure.tts.fake import FAKE_TTS_PROVIDER_ID, fake_tts_descriptor

Args = dict[str, Any]
BASE: Args = {
    "text": "Hello there.",
    "provider_id": FAKE_TTS_PROVIDER_ID,
    "model_id": "tone",
    "voice_id": "tone-low",
}


def _args(override: Args) -> Args:
    return {**BASE, **override}


def _fail_code(create: CreateSynthesisJob, **override: Any) -> SynthesisJobFailureCode:
    with pytest.raises(SynthesisJobError) as caught:
        create.execute(**_args(override))
    return caught.value.code


def _complete(jobs: MemoryJobs, audio: MemoryAudio, created: CreatedSynthesis) -> None:
    job = created.job
    job = job.transition_to(SynthesisJobState.RUNNING, at=job.updated_at)
    job = job.with_chunks_done(job.chunks_total, at=job.updated_at)
    job = job.transition_to(SynthesisJobState.PERSISTING, at=job.updated_at)
    job = job.transition_to(SynthesisJobState.COMPLETED, at=job.updated_at)
    jobs.save(job)
    audio.add(
        SynthesizedAudio(
            job_id=job.id,
            relative_path=f"{job.id}/audio.wav",
            duration_ms=1000,
            sample_rate=16_000,
            chunk_count=job.chunks_total,
            sha256="a" * 64,
            size_bytes=44,
        )
    )


def test_creates_queued_job_with_model_snapshot(
    create: CreateSynthesisJob, jobs: MemoryJobs
) -> None:
    created = create.execute(**BASE, language="en", speed=1.25)

    assert not created.reused
    assert created.audio is None
    assert created.job.state is SynthesisJobState.QUEUED
    assert created.job.chunks_total == 1
    assert created.job.request.speed == 1.25
    assert created.job.request.language == "en"
    assert jobs.get(created.job.id) == created.job


def test_long_text_is_chunked_with_the_engine_limit(create: CreateSynthesisJob) -> None:
    text = "One short sentence. " * 8  # engine limit in the fixture is 40 chars

    created = create.execute(**_args({"text": text}))

    assert created.job.chunks_total > 1
    assert created.job.request.text == text.strip()


def test_unknown_provider(create: CreateSynthesisJob) -> None:
    assert (
        _fail_code(create, provider_id="nope")
        is SynthesisJobFailureCode.PROVIDER_NOT_FOUND
    )


def test_unknown_model_or_model_without_synthesis(
    make_create: Callable[..., CreateSynthesisJob],
) -> None:
    stt_only = replace(
        fake_tts_descriptor(), capabilities=frozenset({ModelCapability.TRANSCRIPTION})
    )
    create = make_create(
        ModelRegistration(stt_only, InstallationStatus.REGISTERED, True)
    )

    assert _fail_code(create) is SynthesisJobFailureCode.MODEL_UNKNOWN
    assert _fail_code(create, model_id="other") is SynthesisJobFailureCode.MODEL_UNKNOWN


@pytest.mark.parametrize(
    "registration",
    [
        ModelRegistration(fake_tts_descriptor(), InstallationStatus.NOT_REGISTERED),
        ModelRegistration(fake_tts_descriptor(), InstallationStatus.REGISTERED, False),
    ],
)
def test_model_not_installed(
    make_create: Callable[..., CreateSynthesisJob], registration: ModelRegistration
) -> None:
    create = make_create(registration)

    assert _fail_code(create) is SynthesisJobFailureCode.MODEL_NOT_INSTALLED


def test_unknown_voice(create: CreateSynthesisJob, jobs: MemoryJobs) -> None:
    assert (
        _fail_code(create, voice_id="ghost") is SynthesisJobFailureCode.VOICE_NOT_FOUND
    )
    assert jobs.items == {}


@pytest.mark.parametrize(
    "override",
    [{"text": "   "}, {"text": "x" * 20_001}, {"speed": 9.0}, {"language": " "}],
)
def test_invalid_request_is_a_typed_error(
    create: CreateSynthesisJob, jobs: MemoryJobs, override: Args
) -> None:
    assert _fail_code(create, **override) is SynthesisJobFailureCode.REQUEST_INVALID
    assert jobs.items == {}


def test_completed_identical_request_is_reused(
    create: CreateSynthesisJob, jobs: MemoryJobs, audio: MemoryAudio
) -> None:
    first = create.execute(**BASE)
    _complete(jobs, audio, first)

    again = create.execute(**BASE)

    assert again.reused
    assert again.job.id == first.job.id
    assert again.audio is not None
    assert len(jobs.items) == 1


@pytest.mark.parametrize(
    "override",
    [
        {"text": "Hello there!"},
        {"voice_id": "tone-high"},
        {"speed": 1.5},
        {"language": "es"},
    ],
)
def test_any_change_of_the_request_is_not_reused(
    create: CreateSynthesisJob,
    jobs: MemoryJobs,
    audio: MemoryAudio,
    override: Args,
) -> None:
    _complete(jobs, audio, create.execute(**BASE))

    other = create.execute(**_args(override))

    assert not other.reused
    assert len(jobs.items) == 2


def test_reuse_does_not_depend_on_how_much_history_followed_it(
    create: CreateSynthesisJob, jobs: MemoryJobs, audio: MemoryAudio
) -> None:
    first = create.execute(**BASE)
    _complete(jobs, audio, first)
    for number in range(600):  # far beyond the old newest-500 scan
        create.execute(**_args({"text": f"Unrelated {number}."}))

    again = create.execute(**BASE)

    assert again.reused
    assert again.job.id == first.job.id


def test_failed_job_or_missing_audio_is_not_reused(
    create: CreateSynthesisJob, jobs: MemoryJobs, audio: MemoryAudio
) -> None:
    failed = create.execute(**BASE).job
    running = failed.transition_to(SynthesisJobState.RUNNING, at=failed.updated_at)
    jobs.save(running.transition_to(SynthesisJobState.FAILED, error_code="boom"))

    retry = create.execute(**BASE)
    _complete(jobs, audio, retry)
    audio.items.clear()  # a completed job whose audio row vanished

    assert not retry.reused
    assert not create.execute(**BASE).reused


def test_identical_job_in_progress_is_returned_not_duplicated(
    create: CreateSynthesisJob, jobs: MemoryJobs
) -> None:
    first = create.execute(**BASE)

    second = create.execute(**BASE)

    assert second.reused
    assert second.audio is None
    assert second.job.id == first.job.id
    assert len(jobs.items) == 1


def test_simultaneous_identical_requests_create_one_job(
    create: CreateSynthesisJob, jobs: MemoryJobs
) -> None:
    barrier = threading.Barrier(6)
    results: list[CreatedSynthesis] = []

    def worker() -> None:
        barrier.wait()
        results.append(create.execute(**BASE))

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(jobs.items) == 1
    assert sum(not item.reused for item in results) == 1


def test_request_hash_is_stable_and_discriminates(
    create: CreateSynthesisJob,
) -> None:
    a = create.execute(**BASE).job.request
    b = create.execute(**_args({"voice_id": "silence"})).job.request

    assert request_hash(a) == request_hash(replace(a))
    assert request_hash(a) != request_hash(b)
    assert request_hash(a) != request_hash(replace(a, model_revision="b" * 40))
    assert len(request_hash(a)) == 64
