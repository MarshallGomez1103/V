"""Checkpoint benchmark contracts with synthetic audio and a fake ASR provider."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import signal
import sys
import time
import wave
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import BinaryIO

import pytest

from voz.application.ports.model_installation import ModelFile
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionOptions,
    TranscriptionResult,
    TranscriptionSegment,
    TranscriptionWord,
)
from voz.infrastructure.asr.catalog import faster_whisper_catalog

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/benchmark-checkpoints.py"
SPEC = importlib.util.spec_from_file_location("checkpoint_benchmark", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
bench = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bench
SPEC.loader.exec_module(bench)


def write_wav(path: Path, seconds: int) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(bytes(seconds * 32_000))


def test_default_only_plans_without_loading_or_spawning(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("planning must not spawn a process")

    monkeypatch.setattr(bench.subprocess, "Popen", forbidden)
    assert bench.main([]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "planned"
    assert plan["results"] is None
    assert plan["baseline_chunk_minutes"] == 30
    assert plan["trial_timeout_seconds"] == 300
    assert [
        (item["minutes"], item["chunks"], item["overlap_seconds"])
        for item in plan["configurations"]
    ] == [(10, 4, 30), (15, 3, 20), (30, 2, 10)]
    assert plan["boundary_centers_ms"] == [600_000, 900_000, 1_200_000, 1_800_000]


@pytest.mark.parametrize("timeout", ["0", "301", "nan", "inf", "-1"])
def test_rejects_unbounded_or_excessive_timeout(timeout: str) -> None:
    assert bench.main(["--timeout-seconds", timeout]) == 2


def test_run_requires_explicit_model_and_external_output(tmp_path: Path) -> None:
    assert bench.main(["--run"]) == 2
    assert (
        bench.main(
            ["--run", "--model-dir", str(tmp_path), "--output-dir", str(SCRIPT.parent)]
        )
        == 2
    )


def test_corpus_is_synthetic_and_speech_crosses_the_cut(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_synthesis(text: str, path: Path) -> None:
        write_wav(path, 2)

    monkeypatch.setattr(bench, "synthesize_phrase", fake_synthesis)
    corpus = bench.make_corpus(tmp_path, duration_ms=65_000)
    assert corpus.duration_ms == 65_000
    assert any(item.start_ms < 30_000 < item.end_ms for item in corpus.utterances)
    with wave.open(str(corpus.audio), "rb") as audio:
        assert audio.getnframes() == 65 * 16_000
        assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (
            1,
            2,
            16_000,
        )
    assert all(item.end_ms <= corpus.duration_ms for item in corpus.utterances)


def test_boundary_score_reports_observed_missing_words() -> None:
    utterances = (bench.Utterance(9_000, 11_000, "hola mundo"),)
    result = TranscriptionResult(
        (
            TranscriptionSegment(
                9_000,
                10_000,
                "hola",
                words=(TranscriptionWord(9_000, 10_000, "hola"),),
            ),
        ),
        "es",
    )
    quality = bench.score_boundary(result, utterances, 10_000, radius_ms=3_000)
    assert quality["wer"] == 0.5
    assert quality["word_edits"] == 1
    assert quality["reference_words"] == 2
    assert quality["hypothesis"] == "hola"


def test_missing_word_timestamps_are_unavailable_not_perfect() -> None:
    result = TranscriptionResult(
        (TranscriptionSegment(9_000, 11_000, "hola mundo"),), "es"
    )
    quality = bench.score_boundary(
        result, (bench.Utterance(9_000, 11_000, "hola mundo"),), 10_000
    )
    assert quality["wer"] is None
    assert quality["reason"] == "word_timestamps_unavailable"


class FakeProvider:
    provider_id = "faster-whisper"

    def __init__(self) -> None:
        self.calls = 0

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        self.calls += 1
        assert options.word_timestamps
        with wave.open(audio, "rb") as handle:
            assert handle.getnframes() > 0
        return TranscriptionResult(
            (
                TranscriptionSegment(
                    0,
                    1_000,
                    "hola",
                    words=(TranscriptionWord(0, 1_000, "hola"),),
                ),
            ),
            "es",
        )


def test_fake_trial_uses_real_durable_checkpoints(tmp_path: Path) -> None:
    path = tmp_path / "fixture.wav"
    write_wav(path, 31)
    corpus = bench.Corpus(path, 31_000, (bench.Utterance(0, 1_000, "hola"),))
    provider = FakeProvider()
    descriptor = faster_whisper_catalog()[0].descriptor
    report = bench.run_configuration(
        provider,
        descriptor,
        corpus,
        tmp_path / "checkpoints.sqlite3",
        chunk_duration_ms=10_000,
        overlap_ms=1_000,
    )
    assert provider.calls == 4
    assert report["checkpoints"] == 4
    assert report["durable_checkpoints"] == 4
    assert report["processed_audio_seconds"] == 37
    assert report["checkpoint_seconds"] >= 0
    assert report["inference_seconds"] >= 0
    assert report["wall_seconds"] >= report["inference_seconds"]


def test_timeout_reaps_its_child(tmp_path: Path) -> None:
    result = bench.run_limited(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        tmp_path,
        dict(os.environ),
        timeout_s=0.1,
    )
    assert result["status"] == "timed_out"
    assert result["returncode"] is not None
    assert result["reaped"] is True


def test_snapshot_checks_revision_hash_and_cache_containment(tmp_path: Path) -> None:
    entry = faster_whisper_catalog()[0]
    entry = replace(
        entry, files=(ModelFile("model.bin", 3, hashlib.sha256(b"abc").hexdigest()),)
    )
    revision = entry.descriptor.revision
    assert revision is not None
    path = tmp_path / "models--fixture" / "snapshots" / revision
    path.mkdir(parents=True)
    weight = path / "model.bin"
    weight.write_bytes(b"abc")
    bench.verify_snapshot(path, entry)
    weight.write_bytes(b"bad")
    with pytest.raises(ValueError, match="hash"):
        bench.verify_snapshot(path, entry)
    weight.unlink()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"abc")
    weight.symlink_to(outside)
    with pytest.raises(ValueError, match="repository"):
        bench.verify_snapshot(path, entry)


def test_failed_child_is_reaped_without_becoming_a_measurement(tmp_path: Path) -> None:
    result = bench.run_limited(
        [sys.executable, "-c", "raise SystemExit(7)"],
        tmp_path,
        dict(os.environ),
        timeout_s=2,
    )
    assert result["status"] == "failed"
    assert result["returncode"] == 7
    assert result["reaped"] is True


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit, RuntimeError])
@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group cleanup")
def test_interruptions_always_clean_group_and_use_bounded_reap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interruption: type[BaseException],
) -> None:
    class Child:
        pid = 123_456_789
        returncode: int | None = None

        def __init__(self) -> None:
            self.waits: list[float | None] = []

        def wait(self, timeout: float | None = None) -> int:
            self.waits.append(timeout)
            if len(self.waits) == 1:
                raise interruption()
            self.returncode = -signal.SIGKILL
            return self.returncode

        def poll(self) -> int | None:
            return self.returncode

        def __enter__(self) -> Child:
            return self

        def __exit__(self, *args: object) -> None:
            self.wait()

    child = Child()
    kills: list[tuple[int, int]] = []

    def spawn(*args: object, **kwargs: object) -> Child:
        return child

    def kill_group(pid: int, sig: int) -> None:
        kills.append((pid, sig))

    monkeypatch.setattr(bench.subprocess, "Popen", spawn)
    monkeypatch.setattr(bench.os, "killpg", kill_group)
    with pytest.raises(interruption):
        bench.run_limited(["unused"], tmp_path, dict(os.environ), timeout_s=1)
    assert kills == [(child.pid, signal.SIGKILL)]
    assert child.returncode == -signal.SIGKILL
    assert all(timeout is not None and timeout <= 5 for timeout in child.waits)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group cleanup")
def test_cleanup_tolerates_group_already_gone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def gone(pid: int, sig: int) -> None:
        calls.append(pid)
        raise ProcessLookupError()

    monkeypatch.setattr(bench.os, "killpg", gone)
    result = bench.run_limited(
        [sys.executable, "-c", "pass"], tmp_path, dict(os.environ), timeout_s=2
    )
    assert calls
    assert result["status"] == "completed" and result["reaped"] is True


@pytest.mark.skipif(sys.platform != "linux", reason="Linux process-group check")
def test_successful_leader_does_not_leave_a_running_descendant(tmp_path: Path) -> None:
    program = (
        "import subprocess,sys; from pathlib import Path; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)']); "
        "Path('descendant.pid').write_text(str(p.pid))"
    )
    result = bench.run_limited(
        [sys.executable, "-c", program], tmp_path, dict(os.environ), timeout_s=2
    )
    pid = int((tmp_path / "descendant.pid").read_text())
    status = Path(f"/proc/{pid}/stat")
    try:
        for _ in range(100):
            if (
                not status.exists()
                or status.read_text().split(")", 1)[1].split()[0] == "Z"
            ):
                break
            time.sleep(0.01)
        assert (
            not status.exists() or status.read_text().split(")", 1)[1].split()[0] == "Z"
        )
    finally:
        with suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
    assert result["reaped"] is True
