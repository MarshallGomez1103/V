"""Plan a synthetic Spanish diarization comparison; --run explicitly executes it.

Requires existing model files, espeak-ng and FFmpeg. Each CPU trial is supervised
for at most 60 seconds. Output must be a new directory outside any Git checkout.
No downloads, speaker-count hints, real recordings or default-threshold changes.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import signal
import subprocess
import sys
import time
import wave
from collections import defaultdict
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

THRESHOLDS = (0.3, 0.4, 0.5, 0.6, 0.7)
MODEL_FILES = (
    "pyannote-segmentation-3-0.onnx",
    "wespeaker_en_voxceleb_resnet34_LM.onnx",
)
RATE = 16_000
TEXTS = (
    "Aquí comienza una muestra breve para comparar las voces.",
    "Ahora habla una segunda voz con un mensaje diferente.",
    "Regresa la primera voz y termina la prueba de sonido.",
)
REPO = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Span:
    start_ms: int
    end_ms: int
    label: str


def external(path: Path) -> Path:
    path = Path(os.path.abspath(path.expanduser()))
    if path.is_relative_to(Path.home() / ".local/share/voz"):
        raise ValueError("personal application data is excluded")
    if any(part.is_symlink() for part in reversed((path, *path.parents))):
        raise ValueError("symlink paths are not accepted")
    path = path.resolve()
    if any((part / ".git").exists() for part in (path, *path.parents)):
        raise ValueError("path must be outside Git checkouts")
    if path.is_relative_to(Path.home() / ".local/share/voz"):
        raise ValueError("personal application data is excluded")
    return path


def validate_paths(model: Path, output: Path) -> tuple[Path, Path]:
    model, output = external(model), external(output)
    if output.exists() or output.is_relative_to(model):
        raise ValueError("output must be a new independent directory")
    if not model.is_dir() or any(
        (model / name).is_symlink() or not (model / name).is_file()
        for name in MODEL_FILES
    ):
        raise ValueError("two existing regular model files are required")
    return model, output


def model_hashes(model: Path) -> dict[str, str]:
    hashes = {}
    for name in MODEL_FILES:
        if (model / name).is_symlink() or not (model / name).is_file():
            raise ValueError("models must be regular files")
        with (model / name).open("rb") as handle:
            hashes[name] = hashlib.file_digest(handle, "sha256").hexdigest()
    return hashes


def isolated_env(directory: Path) -> dict[str, str]:
    env = dict(os.environ)
    for key, name in (
        ("HOME", "home"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_STATE_HOME", "state"),
        ("XDG_RUNTIME_DIR", "runtime"),
        ("HF_HOME", "hf"),
        ("TMPDIR", "tmp"),
    ):
        path = directory / name
        path.mkdir(mode=0o700)
        env[key] = str(path)
    env.update(
        PYTHONPATH=str(REPO / "src"),
        PYTHONDONTWRITEBYTECODE="1",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        VOZ_FFMPEG_AUTO_DOWNLOAD="0",
        CUDA_VISIBLE_DEVICES="",
        OMP_NUM_THREADS="2",
        OPENBLAS_NUM_THREADS="2",
        MKL_NUM_THREADS="2",
        NUMEXPR_NUM_THREADS="2",
    )
    return env


def run_limited(
    command: Sequence[str],
    directory: Path,
    env: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    with (
        (directory / "stdout.log").open("wb") as out,
        (directory / "stderr.log").open("wb") as err,
    ):
        child = subprocess.Popen(
            command,
            cwd=directory,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            start_new_session=True,
        )
        status = "completed"
        try:
            child.wait(timeout=max(0, timeout - (time.perf_counter() - started)))
        except subprocess.TimeoutExpired:
            status = "timed_out"
        finally:
            with suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=2)
        if child.returncode and status != "timed_out":
            status = "failed"
    return {
        "status": status,
        "returncode": child.returncode,
        "reaped": child.poll() is not None,
        "elapsed_seconds": time.perf_counter() - started,
        "argv": list(command),
    }


def score(turns: Sequence[Span], reference: Sequence[Span]) -> dict[str, Any]:
    assignments = []
    for expected in reference:
        overlap: dict[str, int] = defaultdict(int)
        for turn in turns:
            milliseconds = max(
                0,
                min(turn.end_ms, expected.end_ms)
                - max(turn.start_ms, expected.start_ms),
            )
            if milliseconds:
                overlap[turn.label] += milliseconds
        maximum = max(overlap.values(), default=0)
        winners = [label for label, value in overlap.items() if value == maximum]
        assignments.append(
            {
                **asdict(expected),
                "overlap_ms_by_cluster": dict(overlap),
                "dominant_cluster": winners[0] if len(winners) == 1 else None,
            }
        )
    return {
        "cluster_count": len({turn.label for turn in turns}),
        "utterances": assignments,
    }


def make_corpus(
    directory: Path, voices: Sequence[str], env: dict[str, str]
) -> dict[str, Any]:
    directory.mkdir()
    pcm = bytearray(bytes(RATE))  # half a second of initial silence, PCM16
    reference = []
    commands = []
    for index, (text, voice) in enumerate(zip(TEXTS, voices, strict=True)):
        phrase = directory / f"phrase-{index}"
        phrase.mkdir()
        native, normalized = phrase / "native.wav", phrase / "normalized.wav"
        for command in (
            ["espeak-ng", "-v", voice, "-s", "165", "-w", str(native), text],
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
                str(normalized),
            ],
        ):
            lifecycle = run_limited(command, phrase, env, 10)
            commands.append(lifecycle)
            if lifecycle["status"] != "completed":
                raise ValueError("synthetic corpus generation failed")
        with wave.open(str(normalized), "rb") as audio:
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (
                1,
                2,
                RATE,
            ):
                raise ValueError("unexpected synthetic PCM format")
            samples = audio.readframes(audio.getnframes())
        if not samples:
            raise ValueError("synthetic utterance is empty")
        start = len(pcm) * 1000 // (RATE * 2)
        pcm.extend(samples)
        end = len(pcm) * 1000 // (RATE * 2)
        reference.append(Span(start, end, voice))
        pcm.extend(bytes(RATE))
    if not 0 < len(pcm) <= 30 * RATE * 2:
        raise ValueError("synthetic corpus exceeds 30 seconds")
    audio_path = directory / "synthetic.wav"
    with wave.open(str(audio_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(RATE)
        audio.writeframes(pcm)
    result = {
        "audio": str(audio_path),
        "audio_sha256": hashlib.sha256(audio_path.read_bytes()).hexdigest(),
        "audio_seconds": len(pcm) / (RATE * 2),
        "utterances": [asdict(span) for span in reference],
        "texts": TEXTS,
        "text_sha256": hashlib.sha256("\n".join(TEXTS).encode()).hexdigest(),
        "commands": commands,
    }
    (directory / "corpus.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2)
    )
    return result


def worker(model: Path, output: Path, corpus_path: Path, threshold: float) -> None:
    # Native inference stays in this supervised child; no native imports in planning.
    def no_network(event: str, values: tuple[object, ...]) -> None:
        if event == "socket.connect":
            raise RuntimeError("network is disabled for this benchmark")

    sys.addaudithook(no_network)
    from voz.application.diarization_cleanup import merge_residual_clusters
    from voz.application.ports.diarization import DiarizationOptions
    from voz.infrastructure.diarization.sherpa import SherpaOnnxDiarizationProvider

    corpus = json.loads(corpus_path.read_text())
    audio_path = Path(corpus["audio"])
    audio_before = hashlib.sha256(audio_path.read_bytes()).hexdigest()
    if audio_before != corpus["audio_sha256"]:
        raise ValueError("audio differs from generated corpus")
    before = model_hashes(model)
    provider = SherpaOnnxDiarizationProvider(
        segmentation_model=model / MODEL_FILES[0],
        embedding_model=model / MODEL_FILES[1],
        threshold=threshold,
        num_threads=2,
        merge_residual=False,
    )
    started = time.perf_counter()
    try:
        with audio_path.open("rb") as audio:
            raw = provider.diarize(audio=audio, options=DiarizationOptions()).turns
        seconds = time.perf_counter() - started
        clean = merge_residual_clusters(raw, keep_at_least=1)
    finally:
        provider.close()
    if model_hashes(model) != before:
        raise ValueError("model files changed during inference")
    if hashlib.sha256(audio_path.read_bytes()).hexdigest() != audio_before:
        raise ValueError("audio changed during inference")
    reference = [Span(**item) for item in corpus["utterances"]]
    result = {
        "threshold": threshold,
        "wall_seconds": seconds,
        "wall_method": "provider diarize including native load; cleanup excluded",
        "model_sha256": before,
        "audio_sha256": audio_before,
        "audio_file_unchanged": True,
        "raw_turns": [asdict(turn) for turn in raw],
        "post_cleanup_turns": [asdict(turn) for turn in clean],
        "cleanup": "provider automatic stage: merge_residual_clusters(keep_at_least=1)",
        "runtime_versions": {
            name: importlib.metadata.version(name)
            for name in ("sherpa-onnx", "sherpa-onnx-core", "numpy")
        },
        "python": sys.version.split()[0],
    }
    for name, turns in (("raw", raw), ("post_cleanup", clean)):
        result[name] = score(
            [Span(turn.start_ms, turn.end_ms, turn.cluster) for turn in turns],
            reference,
        )
    (output / "result.json").write_text(json.dumps(result, indent=2))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=60)
    parser.add_argument("--single-voice-control", action="store_true")
    parser.add_argument(
        "--worker", type=float, choices=THRESHOLDS, help=argparse.SUPPRESS
    )
    parser.add_argument("--corpus", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if (
            not math.isfinite(args.timeout_seconds)
            or not 0 < args.timeout_seconds <= 60
        ):
            raise ValueError("deadline must be positive and at most 60 seconds")
        plan: dict[str, Any] = {
            "schema_version": 1,
            "status": "planned",
            "thresholds": THRESHOLDS,
            "device": "cpu",
            "threads": 2,
            "results": None,
            "timeout_seconds": args.timeout_seconds,
            "corpora": ["aba", "aaa"] if args.single_voice_control else ["aba"],
            "limitations": [
                "synthetic Spanish espeak-ng; one sample per configuration",
                "nominal windows include synthesized silence; not DER or real accuracy",
                "labels are not identities; no universal threshold recommendation",
                "cluster overlaps are independent sums, not a partition of speech time",
            ],
        }
        if not args.run:
            print(json.dumps(plan, indent=2))
            return 0
        if os.name != "posix" or args.model_dir is None or args.output_dir is None:
            raise ValueError(
                "POSIX, explicit model-dir and new output-dir are required"
            )
        if args.worker is not None:
            if args.corpus is None:
                raise ValueError("private worker requires corpus")
            worker(
                external(args.model_dir),
                external(args.output_dir),
                external(args.corpus),
                args.worker,
            )
            return 0
        model, output = validate_paths(args.model_dir, args.output_dir)
        before = model_hashes(model)
        output.mkdir(parents=True, mode=0o700)
        preparation = output / "preparation"
        preparation.mkdir()
        env = isolated_env(preparation)
        versions = {}
        for tool in ("espeak-ng", "ffmpeg"):
            check = output / f"version-{tool}"
            check.mkdir()
            result = run_limited(
                [tool, "--version" if tool == "espeak-ng" else "-version"],
                check,
                env,
                10,
            )
            if result["status"] != "completed":
                raise ValueError("required local executable unavailable")
            versions[tool] = (check / "stdout.log").read_text()
        results = []
        for name in plan["corpora"]:
            voices = ("es+f3", "es+m3", "es+f3") if name == "aba" else ("es+f3",) * 3
            corpus = make_corpus(output / name, voices, env)
            for threshold in THRESHOLDS:
                trial = output / f"{name}-{threshold:.1f}"
                trial.mkdir()
                command = [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--run",
                    "--model-dir",
                    str(model),
                    "--output-dir",
                    str(trial),
                    "--worker",
                    str(threshold),
                    "--corpus",
                    str(output / name / "corpus.json"),
                ]
                lifecycle = run_limited(
                    command, trial, isolated_env(trial), args.timeout_seconds
                )
                measurement = trial / "result.json"
                audio_unchanged = (
                    hashlib.sha256(Path(corpus["audio"]).read_bytes()).hexdigest()
                    == corpus["audio_sha256"]
                )
                if lifecycle["status"] == "completed" and (
                    not measurement.is_file() or not audio_unchanged
                ):
                    lifecycle["status"] = "failed"
                results.append(
                    {
                        "corpus": name,
                        **lifecycle,
                        "measurement": json.loads(measurement.read_text())
                        if lifecycle["status"] == "completed"
                        else None,
                        "audio_sha256": corpus["audio_sha256"],
                        "audio_file_unchanged": audio_unchanged,
                    }
                )
                report = {
                    **plan,
                    "status": "partial",
                    "results": results,
                    "model_sha256": before,
                    "tool_versions": versions,
                }
                (output / "report.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2)
                )
                print(
                    json.dumps(
                        {
                            "corpus": name,
                            "threshold": threshold,
                            "status": lifecycle["status"],
                        }
                    ),
                    flush=True,
                )
        unchanged = model_hashes(model) == before
        success = unchanged and all(item["status"] == "completed" for item in results)
        report.update(
            status="completed" if success else "partial",
            model_files_unchanged=unchanged,
        )
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2)
        )
        return 0 if success else 1
    except (ValueError, OSError, subprocess.SubprocessError, ImportError, wave.Error):
        print(
            "diarization_benchmark_failed: invalid configuration or local failure",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
