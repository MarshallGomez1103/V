"""Compare 10/15/30 minute ASR checkpoints using generated Spanish speech.

Planning is the default. Execution requires --run, --model-dir and an unused
--output-dir outside the checkout. Each isolated CPU/int8 trial has a hard
timeout of at most 300 seconds, including preparation, load and scoring.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import math
import os
import signal
import subprocess
import sys
import time
import wave
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from sqlalchemy import Engine

from voz.application.asr_device_selection import ComputeDevice, ExecutionDecision
from voz.application.chunked_transcription import plan_audio_chunks
from voz.application.evaluation import character_error_rate, word_error_rate
from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionClip,
    TranscriptionOptions,
    TranscriptionProvider,
    TranscriptionResult,
)
from voz.application.ports.transcription_checkpoint import TranscriptionCheckpoint
from voz.application.recoverable_transcription import RecoverableTranscription
from voz.domain.entities.media_asset import MediaAsset
from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.domain.entities.processing_profile import ComputePrecision
from voz.domain.entities.project import Project
from voz.domain.entities.transcription_job import (
    TranscriptionJob,
    TranscriptionJobState,
)
from voz.infrastructure.asr.catalog import CatalogEntry, faster_whisper_catalog
from voz.infrastructure.asr.faster_whisper import FasterWhisperProvider
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import (
    SqliteMediaAssetRepository,
    SqliteProjectRepository,
    SqliteTranscriptionJobRepository,
)
from voz.infrastructure.persistence.schema import metadata
from voz.infrastructure.persistence.transcription_checkpoints import (
    SqliteTranscriptionCheckpointStore,
)

MINUTES = (10, 15, 30)
OVERLAP_MS = 5_000
RATE = 16_000
REPO = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Utterance:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class Corpus:
    audio: Path
    duration_ms: int
    utterances: tuple[Utterance, ...]


def boundary_centers(duration_ms: int) -> list[int]:
    return sorted(
        {
            chunk.owned_end_ms
            for minutes in MINUTES
            for chunk in plan_audio_chunks(
                duration_ms, chunk_duration_ms=minutes * 60_000
            )
            if chunk.owned_end_ms < duration_ms
        }
    )


def plan_report(
    duration_ms: int, timeout_s: float, entry: CatalogEntry
) -> dict[str, object]:
    configurations: list[dict[str, object]] = []
    for minutes in MINUTES:
        chunks = plan_audio_chunks(duration_ms, chunk_duration_ms=minutes * 60_000)
        configurations.append(
            {
                "minutes": minutes,
                "chunks": len(chunks),
                "overlap_seconds": (
                    sum(c.process_end_ms - c.process_start_ms for c in chunks)
                    - duration_ms
                )
                / 1_000,
            }
        )
    return {
        "schema_version": 1,
        "status": "planned",
        "results": None,
        "baseline_chunk_minutes": 30,
        "trial_timeout_seconds": timeout_s,
        "audio_seconds": duration_ms / 1_000,
        "planned_pcm_bytes": duration_ms * 32,
        "model_id": entry.descriptor.model_id,
        "source": entry.descriptor.source,
        "revision": entry.descriptor.revision,
        "device": "cpu",
        "compute_type": "int8",
        "configurations": configurations,
        "boundary_centers_ms": boundary_centers(duration_ms),
    }


def synthesize_phrase(text: str, output: Path) -> None:
    native = output.with_suffix(".native.wav")
    for command in (
        ["espeak-ng", "-v", "es", "-s", "160", "-w", str(native), text],
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(native),
            "-ar",
            str(RATE),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output),
        ],
    ):
        subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=True,
            timeout=10,
        )


def make_corpus(directory: Path, *, duration_ms: int) -> Corpus:
    """Place full utterances across every candidate boundary, with silence between.

    Reference timing is utterance-level, not forced alignment. Every phrase is
    contained inside a +/-15 second window around its center.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "synthetic.wav"
    utterances: list[Utterance] = []
    colors = ("azul", "verde", "roja", "blanca", "negra", "gris", "violeta", "naranja")
    nouns = ("señal", "lectura", "muestra", "medida", "onda", "prueba", "curva", "nota")
    cursor = 0
    total_frames = duration_ms * RATE // 1_000
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(RATE)
        for index, center in enumerate([5_000, *range(30_000, duration_ms, 30_000)]):
            text = (
                f"La {nouns[index % len(nouns)]} "
                f"{colors[(index // len(nouns)) % len(colors)]} "
                "permite comparar un registro estable con una observación reciente."
            )
            phrase = directory / f"phrase-{index:03d}.wav"
            synthesize_phrase(text, phrase)
            with wave.open(str(phrase), "rb") as audio:
                if (
                    audio.getnchannels(),
                    audio.getsampwidth(),
                    audio.getframerate(),
                ) != (1, 2, RATE):
                    raise ValueError("synthetic phrase must be mono PCM16 at 16 kHz")
                frames = audio.getnframes()
                pcm = audio.readframes(frames)
            start = center * RATE // 1_000 - frames // 2
            if frames > 20 * RATE or start < cursor or start + frames > total_frames:
                raise ValueError("synthetic phrase does not fit its reference window")
            output.writeframesraw(bytes((start - cursor) * 2))
            output.writeframesraw(pcm)
            cursor = start + frames
            utterances.append(
                Utterance(start * 1_000 // RATE, cursor * 1_000 // RATE, text)
            )
        output.writeframesraw(bytes((total_frames - cursor) * 2))
    (directory / "reference.json").write_text(
        json.dumps(
            [
                {"start_ms": u.start_ms, "end_ms": u.end_ms, "text": u.text}
                for u in utterances
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return Corpus(path, duration_ms, tuple(utterances))


def score_text(reference: str, hypothesis: str) -> dict[str, object]:
    wer, cer = (
        word_error_rate(reference, hypothesis),
        character_error_rate(reference, hypothesis),
    )
    return {
        "wer": wer.rate,
        "cer": cer.rate,
        "word_edits": wer.edits,
        "reference_words": wer.reference_length,
        "char_edits": cer.edits,
        "reference_chars": cer.reference_length,
    }


def score_boundary(
    result: TranscriptionResult,
    utterances: tuple[Utterance, ...],
    center_ms: int,
    *,
    radius_ms: int = 15_000,
) -> dict[str, object]:
    low, high = center_ms - radius_ms, center_ms + radius_ms
    reference = " ".join(
        u.text for u in utterances if low <= u.start_ms and u.end_ms <= high
    )
    segments = [s for s in result.segments if s.start_ms < high and s.end_ms > low]
    if not reference or any(not s.words for s in segments):
        return {
            "center_ms": center_ms,
            "wer": None,
            "cer": None,
            "reason": "word_timestamps_unavailable"
            if reference
            else "reference_unavailable",
        }
    hypothesis = " ".join(
        w.text
        for s in segments
        for w in s.words
        if low <= (w.start_ms + w.end_ms) / 2 < high
    )
    return {
        "center_ms": center_ms,
        "reference": reference,
        "hypothesis": hypothesis,
        **score_text(reference, hypothesis),
    }


@dataclass
class WavSource:
    path: Path
    seconds: float = 0

    @contextmanager
    def open(self, clip: TranscriptionClip | None = None) -> Generator[BinaryIO]:
        started = time.perf_counter()
        with wave.open(str(self.path), "rb") as audio:
            first = 0 if clip is None else clip.start_ms * RATE // 1_000
            last = audio.getnframes() if clip is None else clip.end_ms * RATE // 1_000
            audio.setpos(first)
            pcm = audio.readframes(last - first)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(RATE)
            output.writeframes(pcm)
        buffer.seek(0)
        self.seconds += time.perf_counter() - started
        with buffer:
            yield buffer


@dataclass
class TimedProvider:
    delegate: TranscriptionProvider
    seconds: float = 0

    @property
    def provider_id(self) -> str:
        return self.delegate.provider_id

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        started = time.perf_counter()
        try:
            return self.delegate.transcribe(
                audio=audio, options=options, cancellation=cancellation
            )
        finally:
            self.seconds += time.perf_counter() - started


class TimedCheckpoints(SqliteTranscriptionCheckpointStore):
    def __init__(self, engine: Engine) -> None:
        super().__init__(engine)
        self.seconds = 0.0
        self.intervals: list[float] = []
        self.previous = time.perf_counter()

    def commit(
        self, checkpoint: TranscriptionCheckpoint, job: TranscriptionJob
    ) -> None:
        started = time.perf_counter()
        super().commit(checkpoint, job)
        ended = time.perf_counter()
        self.seconds += ended - started
        self.intervals.append(ended - self.previous)
        self.previous = ended


def seed_job(engine: Engine, corpus: Corpus) -> TranscriptionJob:
    metadata.create_all(engine)
    now = datetime.now(UTC)
    project = Project("Synthetic checkpoint benchmark", created_at=now)
    asset = MediaAsset(
        project.id,
        hashlib.sha256(corpus.audio.read_bytes()).hexdigest(),
        "synthetic.wav",
        corpus.audio.stat().st_size,
        duration_ms=corpus.duration_ms,
    )
    job = TranscriptionJob.create(
        job_id=uuid4(), project_id=project.id, media_asset_id=asset.id, now=now
    )
    for state in (
        TranscriptionJobState.PROBING,
        TranscriptionJobState.PREPROCESSING,
        TranscriptionJobState.TRANSCRIBING,
    ):
        job = job.transition_to(state, at=now)
    SqliteProjectRepository(engine).add(project)
    SqliteMediaAssetRepository(engine).add(asset)
    SqliteTranscriptionJobRepository(engine).add(job)
    return job


def run_configuration(
    provider: TranscriptionProvider,
    descriptor: ModelDescriptor,
    corpus: Corpus,
    database: Path,
    *,
    chunk_duration_ms: int,
    overlap_ms: int = OVERLAP_MS,
) -> dict[str, object]:
    engine = create_sqlite_engine(database.absolute())
    try:
        job = seed_job(engine, corpus)
        source, timed = WavSource(corpus.audio), TimedProvider(provider)
        checkpoints = TimedCheckpoints(engine)
        started = time.perf_counter()
        checkpoints.previous = started
        outcome = RecoverableTranscription(
            timed, source, checkpoints, SqliteTranscriptionJobRepository(engine)
        ).execute(
            job=job,
            duration_ms=corpus.duration_ms,
            options=TranscriptionOptions(
                model=descriptor, language="es", word_timestamps=True
            ),
            chunk_duration_ms=chunk_duration_ms,
            overlap_ms=overlap_ms,
        )
        wall = time.perf_counter() - started
        persisted = tuple(checkpoints.list_for_job(job.id))
        chunks = plan_audio_chunks(
            corpus.duration_ms,
            chunk_duration_ms=chunk_duration_ms,
            overlap_ms=overlap_ms,
        )
        reference = " ".join(u.text for u in corpus.utterances)
        return {
            "chunk_duration_ms": chunk_duration_ms,
            "n": 1,
            "wall_seconds": wall,
            "inference_seconds": timed.seconds,
            "extraction_seconds": source.seconds,
            "checkpoint_seconds": checkpoints.seconds,
            "other_overhead_seconds": max(
                0, wall - timed.seconds - source.seconds - checkpoints.seconds
            ),
            "max_checkpoint_interval_seconds": max(checkpoints.intervals),
            "rtf": wall / (corpus.duration_ms / 1_000),
            "checkpoints": outcome.completed_chunks,
            "durable_checkpoints": len(persisted),
            "processed_audio_seconds": sum(
                c.process_end_ms - c.process_start_ms for c in chunks
            )
            / 1_000,
            "global_quality": score_text(reference, outcome.result.text),
            "boundary_quality": [
                {
                    **score_boundary(outcome.result, corpus.utterances, center),
                    "is_cut": center % chunk_duration_ms == 0,
                }
                for center in boundary_centers(corpus.duration_ms)
            ],
            "segments_without_words": sum(not s.words for s in outcome.result.segments),
        }
    finally:
        engine.dispose()


def run_limited(
    command: Sequence[str],
    directory: Path,
    environ: dict[str, str],
    *,
    timeout_s: float,
) -> dict[str, object]:
    started = time.perf_counter()
    with (
        (directory / "stdout.log").open("wb") as stdout,
        (directory / "stderr.log").open("wb") as stderr,
    ):
        child = subprocess.Popen(
            command,
            cwd=directory,
            env=environ,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=os.name == "posix",
        )
        status = "completed"
        try:
            child.wait(timeout=max(0, timeout_s - (time.perf_counter() - started)))
        except subprocess.TimeoutExpired:
            status = "timed_out"
        finally:
            try:
                if os.name == "posix":
                    os.killpg(child.pid, signal.SIGKILL)
                elif child.poll() is None:
                    child.kill()
            except ProcessLookupError:
                pass
            child.wait(timeout=5)
        if child.returncode != 0 and status != "timed_out":
            status = "failed"
        return {
            "status": status,
            "returncode": child.returncode,
            "reaped": child.poll() is not None,
            "elapsed_seconds": time.perf_counter() - started,
        }


def verify_snapshot(path: Path, entry: CatalogEntry) -> None:
    if path.parent.name != "snapshots" or path.name != entry.descriptor.revision:
        raise ValueError("model directory must name the pinned HF snapshot revision")
    repository = path.parent.parent
    for item in entry.files:
        candidate = path / item.name
        target = candidate
        if candidate.is_symlink():
            target = Path(os.path.abspath(candidate.parent / os.readlink(candidate)))
        if not target.is_relative_to(repository) or not target.resolve().is_relative_to(
            repository.resolve()
        ):
            raise ValueError("snapshot file must stay in its own HF cache repository")
        if candidate.stat().st_size != item.size_bytes:
            raise ValueError("model snapshot size does not match pinned catalog")
        if item.sha256 is not None:
            with candidate.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            if digest != item.sha256:
                raise ValueError("model snapshot hash does not match pinned catalog")


@dataclass(frozen=True)
class LocalSnapshot:
    directory: Path

    def resolve_path(self, descriptor: ModelDescriptor) -> Path:
        return self.directory


def worker(args: argparse.Namespace, entry: CatalogEntry) -> None:
    # Explicit local snapshots and offline runtime flags prevent model downloads.
    def no_network(event: str, values: tuple[object, ...]) -> None:
        if event == "socket.connect":
            raise RuntimeError("network disabled for checkpoint benchmark")

    sys.addaudithook(no_network)
    directory = Path(args.output_dir)
    verify_snapshot(Path(args.model_dir), entry)
    corpus = make_corpus(
        directory / "corpus", duration_ms=args.duration_minutes * 60_000
    )
    provider = FasterWhisperProvider(
        model_resolver=LocalSnapshot(Path(args.model_dir)),
        execution=ExecutionDecision(ComputeDevice.CPU, ComputePrecision.INT8),
        configured_model=entry.descriptor,
    )
    try:
        with WavSource(corpus.audio).open(TranscriptionClip(0, 1_000)) as silence:
            started = time.perf_counter()
            provider.transcribe(
                audio=silence,
                options=TranscriptionOptions(model=entry.descriptor, language="es"),
            )
            warmup = time.perf_counter() - started
        result = run_configuration(
            provider,
            entry.descriptor,
            corpus,
            directory / "checkpoints.sqlite3",
            chunk_duration_ms=args.worker_minutes * 60_000,
        )
        result.update(
            {
                "warmup_seconds": warmup,
                "catalog_weight_sha256_verified": True,
                "audio_sha256": hashlib.sha256(corpus.audio.read_bytes()).hexdigest(),
                "speech_seconds": sum(u.end_ms - u.start_ms for u in corpus.utterances)
                / 1_000,
            }
        )
        (directory / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    finally:
        provider.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument(
        "--model-id",
        choices=[e.descriptor.model_id for e in faster_whisper_catalog()],
        default="base",
    )
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--duration-minutes", type=int, default=31)
    parser.add_argument("--timeout-seconds", type=float, default=300)
    parser.add_argument(
        "--worker-minutes", type=int, choices=MINUTES, help=argparse.SUPPRESS
    )
    args = parser.parse_args(argv)
    entry = next(
        e for e in faster_whisper_catalog() if e.descriptor.model_id == args.model_id
    )
    try:
        if args.duration_minutes <= 30:
            raise ValueError("audio must exceed 30 minutes to compare all policies")
        if (
            not math.isfinite(args.timeout_seconds)
            or not 0 < args.timeout_seconds <= 300
        ):
            raise ValueError(
                "trial timeout must be greater than zero and at most 300 seconds"
            )
        plan = plan_report(args.duration_minutes * 60_000, args.timeout_seconds, entry)
        if not args.run:
            print(json.dumps(plan, indent=2))
            return 0
        if args.model_dir is None or args.output_dir is None:
            raise ValueError("execution requires model-dir and output-dir")
        model, output = (
            Path(args.model_dir).absolute(),
            Path(args.output_dir).absolute(),
        )
        forbidden = Path.home() / ".local/share/voz"
        if model.is_relative_to(forbidden) or model.resolve().is_relative_to(forbidden):
            raise ValueError("model must be an explicit external cache snapshot")
        if output.is_relative_to(REPO) or output.is_relative_to(forbidden):
            raise ValueError("output must be outside the checkout and application data")
        output = output.resolve()
        if output.is_relative_to(REPO) or output.is_relative_to(forbidden):
            raise ValueError("output must be outside the checkout and application data")
        if args.worker_minutes is not None:
            worker(args, entry)
            return 0
        output.mkdir(parents=True, exist_ok=False)
        results: list[dict[str, object]] = []
        for minutes in (30, 15, 10):
            trial = output / f"chunk-{minutes}"
            trial.mkdir()
            environ = dict(
                os.environ,
                HF_HUB_OFFLINE="1",
                TRANSFORMERS_OFFLINE="1",
                PYTHONDONTWRITEBYTECODE="1",
                PYTHONPATH=str(REPO / "src"),
                HF_HOME=str(trial / "cache" / "huggingface"),
            )
            for name, suffix in (
                ("HOME", "home"),
                ("XDG_DATA_HOME", "data"),
                ("XDG_CONFIG_HOME", "config"),
                ("XDG_CACHE_HOME", "cache"),
                ("XDG_STATE_HOME", "state"),
            ):
                isolated = trial / suffix
                isolated.mkdir()
                environ[name] = str(isolated)
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--run",
                "--model-id",
                args.model_id,
                "--model-dir",
                str(model),
                "--output-dir",
                str(trial),
                "--duration-minutes",
                str(args.duration_minutes),
                "--timeout-seconds",
                str(args.timeout_seconds),
                "--worker-minutes",
                str(minutes),
            ]
            print(
                f"Starting {minutes}-minute policy; timeout {args.timeout_seconds:g}s",
                flush=True,
            )
            lifecycle = run_limited(
                command, trial, environ, timeout_s=args.timeout_seconds
            )
            result_path = trial / "result.json"
            results.append(
                {
                    "minutes": minutes,
                    **lifecycle,
                    "measurement": json.loads(result_path.read_text())
                    if result_path.exists()
                    else None,
                }
            )
            report = {
                **plan,
                "status": "completed"
                if len(results) == 3
                and all(r["status"] == "completed" for r in results)
                else "partial",
                "results": results,
                "environment": {
                    name: importlib.metadata.version(name)
                    for name in ("faster-whisper", "ctranslate2")
                },
                "limitations": [
                    "synthetic sparse espeak-ng Spanish; one speaker; n=1 per policy",
                    "repeated sentence templates, no real-world quality claim",
                    "boundary reference is utterance-level; "
                    "scores use ASR word midpoints in +/-15s windows",
                    "warmup and corpus preparation excluded "
                    "from measured pipeline wall time",
                    "CPU thread count uses the installed runtime default",
                ],
            }
            (output / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(
                f"Finished {minutes}-minute policy: {lifecycle['status']}", flush=True
            )
        return 0 if all(r["status"] == "completed" for r in results) else 1
    except (ValueError, OSError, subprocess.SubprocessError):
        print(
            "checkpoint_benchmark_failed: "
            "invalid configuration or local execution failure",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
