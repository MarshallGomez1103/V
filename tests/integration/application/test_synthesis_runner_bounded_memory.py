"""The synthesis runner streams chunk audio to storage instead of holding it all."""
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportMissingImports=false

from __future__ import annotations

import hashlib
import io
import wave
import weakref
from itertools import pairwise
from pathlib import Path
from typing import Final

import pytest
from test_synthesis_runner import CHUNKS, MAX_CHARS, TEXT, Harness, harness

from voz.application.ports.speech_synthesis import (
    PcmAudio,
    SynthesisCancellationToken,
    SynthesisProgressCallback,
)
from voz.application.text_chunking import silence_gap_ms
from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.domain.entities.synthesis_job import SynthesisJobState
from voz.infrastructure.persistence.synthesis import SqliteSynthesizedAudioRepository
from voz.infrastructure.tts.fake import FakeSpeechSynthesisProvider

RATE: Final = 16_000
CHUNK_BYTES: Final = 400_000  # 12.5 s of PCM16 per chunk, far above any buffer


class _Tracked(PcmAudio):
    """A chunk that can be weakly referenced, to see who still holds it."""


class BigChunkTts(FakeSpeechSynthesisProvider):
    """Deterministic engine delivering large chunks and watching their lifetime."""

    def __init__(self, job_dir: Path | None = None) -> None:
        super().__init__(max_chunk_chars=MAX_CHARS)
        self.job_dir = job_dir
        self.calls = 0
        self.live_at_call: list[int] = []
        self.written_at_call: list[int] = []
        self.pcm: list[bytes] = []
        self._refs: list[weakref.ref[PcmAudio]] = []

    def synthesize(
        self,
        chunk_text: str,
        *,
        model: ModelDescriptor,
        voice_id: str,
        speed: float = 1.0,
        cancellation: SynthesisCancellationToken | None = None,
        on_progress: SynthesisProgressCallback | None = None,
    ) -> PcmAudio:
        self.calls += 1
        self.live_at_call.append(sum(ref() is not None for ref in self._refs))
        self.written_at_call.append(
            sum(
                path.stat().st_size
                for path in (self.job_dir.glob("*.tmp") if self.job_dir else ())
            )
        )
        seed = bytes([self.calls]) * 2
        samples = seed * (CHUNK_BYTES // 2)
        self.pcm.append(samples)
        audio = _Tracked(samples, RATE)
        self._refs.append(weakref.ref(audio))
        return audio


def _job_dir(fixture: Harness) -> Path:
    return fixture.storage._data_root / "synthesis" / str(fixture.job.id)  # pyright: ignore[reportPrivateUsage]


def test_runner_does_not_retain_rendered_chunks_and_writes_incrementally(
    tmp_path: Path,
) -> None:
    probe_dir = tmp_path / "data" / "synthesis"
    fixture = harness(tmp_path)
    provider = BigChunkTts(probe_dir / str(fixture.job.id))
    fixture.runner = fixture.new_runner(provider)  # pyright: ignore[reportArgumentType]

    finished = fixture.runner.run_job(fixture.job.id)

    assert finished is not None and finished.state is SynthesisJobState.COMPLETED
    assert provider.calls == len(CHUNKS) >= 4
    # Before each chunk is rendered, at most the previous one may still be alive.
    assert max(provider.live_at_call) <= 1, provider.live_at_call
    # And the audio already rendered is on disk while the next chunk renders.
    for call, written in enumerate(provider.written_at_call):
        assert written >= call * CHUNK_BYTES, provider.written_at_call
    fixture.engine.dispose()


def test_streamed_wav_is_byte_identical_to_joining_all_chunks(tmp_path: Path) -> None:
    fixture = harness(tmp_path)
    provider = BigChunkTts()
    fixture.runner = fixture.new_runner(provider)  # pyright: ignore[reportArgumentType]

    fixture.runner.run_job(fixture.job.id)

    stored = SqliteSynthesizedAudioRepository(fixture.engine).get_by_job(fixture.job.id)
    assert stored is not None
    expected = io.BytesIO()
    with wave.open(expected, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(RATE)
        for index, pcm in enumerate(provider.pcm):
            writer.writeframes(pcm)
            if index < len(CHUNKS) - 1:
                gap = silence_gap_ms(TEXT[CHUNKS[index].end : CHUNKS[index + 1].start])
                writer.writeframes(bytes(round(gap * RATE / 1000) * 2))
    assert len(list(pairwise(CHUNKS))) == len(CHUNKS) - 1
    with fixture.storage.open_for_reading(stored.relative_path) as handle:
        actual = handle.read()
    assert actual == expected.getvalue()
    assert stored.sha256 == hashlib.sha256(actual).hexdigest()
    assert stored.size_bytes == len(actual)
    fixture.engine.dispose()


@pytest.mark.parametrize("outcome", ["cancel", "failure"])
def test_interrupted_render_leaves_no_temporary_and_no_audio(
    tmp_path: Path, outcome: str
) -> None:
    fixture = harness(tmp_path)

    class Interrupting(BigChunkTts):
        def synthesize(self, *args: object, **kwargs: object) -> PcmAudio:
            audio = super().synthesize(*args, **kwargs)  # pyright: ignore[reportArgumentType]
            if self.calls == 2:
                if outcome == "cancel":
                    fixture.runner.cancel(fixture.job.id)
                else:
                    raise RuntimeError("engine crashed")
            return audio

    provider = Interrupting()
    fixture.runner = fixture.new_runner(provider)  # pyright: ignore[reportArgumentType]

    finished = fixture.runner.run_job(fixture.job.id)

    assert finished is not None
    expected = (
        SynthesisJobState.CANCELLED if outcome == "cancel" else SynthesisJobState.FAILED
    )
    assert finished.state is expected
    assert provider.calls == 2
    assert not _job_dir(fixture).exists()
    assert (
        SqliteSynthesizedAudioRepository(fixture.engine).get_by_job(fixture.job.id)
        is None
    )
    fixture.engine.dispose()
