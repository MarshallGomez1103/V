"""``voz bench``: measure time, memory and WER/CER of a local model (S13.07-S13.10).

The dataset lives outside the checkout (``$XDG_DATA_HOME/voz/benchmarks/<name>/``)
and the model is loaded only from an explicit directory: nothing is downloaded.
"""

from __future__ import annotations

import dataclasses
import importlib.metadata
import io
import json
import platform
import resource
import subprocess
import threading
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import typer

from voz.application.asr_device_selection import ComputeDevice, ExecutionDecision
from voz.application.evaluation import (
    character_error_rate,
    word_error_rate,
)
from voz.application.ports.transcription import (
    TranscriptionError,
    TranscriptionOptions,
    TranscriptionProvider,
)
from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.domain.entities.processing_profile import ComputePrecision
from voz.infrastructure.asr.catalog import faster_whisper_catalog
from voz.infrastructure.asr.faster_whisper import FasterWhisperProvider
from voz.infrastructure.asr.system_resources import read_gpu_memory
from voz.infrastructure.asr.whisper_cpp import (
    WhisperCppProvider,
    probe_whisper_cpp,
)
from voz.infrastructure.asr.whisper_cpp_catalog import whisper_cpp_catalog
from voz.infrastructure.paths import resolve_voz_paths

MANIFEST_NAME = "manifest.json"
SCHEMA_VERSION = 1
_WARMUP_SECONDS = 1
_VRAM_INTERVAL_SECONDS = 0.2


class BenchmarkError(Exception):
    """Stable, path-free benchmark failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class BenchItem:
    audio: Path
    reference: str | None


@dataclass(frozen=True, slots=True)
class Dataset:
    name: str
    language: str | None
    items: tuple[BenchItem, ...]


@dataclass(frozen=True, slots=True)
class ItemResult:
    audio: str
    audio_seconds: float
    wall_seconds: float
    rtf: float
    wer: float | None
    cer: float | None
    word_edits: int | None
    reference_words: int | None
    char_edits: int | None
    reference_chars: int | None


@dataclass(frozen=True, slots=True)
class Totals:
    audio_seconds: float
    wall_seconds: float
    rtf: float
    wer: float | None
    cer: float | None


@dataclass(frozen=True, slots=True)
class Memory:
    ram_peak_mib: float
    ram_delta_mib: float
    vram_peak_mib: int | None
    vram_baseline_mib: int | None
    vram_delta_mib: int | None


@dataclass(frozen=True, slots=True)
class BenchReport:
    schema_version: int
    engine: str
    model_id: str
    source: str | None
    revision: str | None
    device: str
    compute_type: str
    language: str | None
    dataset: str
    load_seconds: float
    totals: Totals
    memory: Memory
    environment: dict[str, str]
    items: tuple[ItemResult, ...]


# -- dataset ----------------------------------------------------------------


def checkout_root() -> Path | None:
    """The source checkout this module runs from, or ``None`` when installed."""
    root = Path(__file__).resolve().parents[4]
    if (root / "pyproject.toml").is_file() and (root / "src" / "voz").is_dir():
        return root
    return None


def ensure_outside_checkout(path: Path, *, repo_root: Path | None) -> None:
    """Refuse benchmark data inside the repository (privacy invariant)."""
    if repo_root is not None and path.resolve().is_relative_to(repo_root.resolve()):
        raise BenchmarkError(
            "benchmark_dataset_inside_checkout",
            "El dataset de benchmark no puede estar dentro del repositorio.",
        )


def resolve_dataset_dir(
    dataset: str, *, benchmarks_dir: Path, repo_root: Path | None
) -> Path:
    """A bare name lives under ``benchmarks_dir``; anything else is a path."""
    is_path = "/" in dataset or "\\" in dataset or dataset.startswith(".")
    directory = Path(dataset).expanduser() if is_path else benchmarks_dir / dataset
    ensure_outside_checkout(directory, repo_root=repo_root)
    ensure_outside_checkout(benchmarks_dir, repo_root=repo_root)
    if not directory.is_dir():
        raise BenchmarkError(
            "benchmark_dataset_not_found", "No existe el dataset indicado."
        )
    return directory


def _inside(base: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative:
        raise BenchmarkError("benchmark_manifest_invalid", "Ruta vacía en el manifest.")
    candidate = (base / relative).resolve()
    if not candidate.is_relative_to(base.resolve()) or not candidate.is_file():
        raise BenchmarkError(
            "benchmark_manifest_invalid",
            "El manifest apunta a un archivo inexistente o fuera del dataset.",
        )
    return candidate


def load_dataset(directory: Path) -> Dataset:
    """Read ``manifest.json``: ``{"language": "es", "items": [{audio, reference}]}``.

    Each item has ``audio`` and, optionally, the reference as inline
    ``reference`` text or a ``reference_file``; paths are relative to the dataset.
    """
    try:
        payload = cast(
            object, json.loads((directory / MANIFEST_NAME).read_text("utf-8"))
        )
    except (OSError, ValueError) as error:
        raise BenchmarkError(
            "benchmark_manifest_invalid", "No se pudo leer manifest.json."
        ) from error
    if not isinstance(payload, dict):
        raise BenchmarkError(
            "benchmark_manifest_invalid", "manifest.json no es un objeto."
        )
    values = cast(dict[str, object], payload)
    language = values.get("language")
    raw_items = values.get("items")
    if not (language is None or isinstance(language, str)) or not (
        isinstance(raw_items, list) and raw_items
    ):
        raise BenchmarkError(
            "benchmark_manifest_invalid", "manifest.json necesita 'items' no vacío."
        )
    items: list[BenchItem] = []
    for raw in cast(list[object], raw_items):
        if not isinstance(raw, dict):
            raise BenchmarkError("benchmark_manifest_invalid", "Item inválido.")
        item = cast(dict[str, object], raw)
        audio = _inside(directory, item.get("audio"))
        reference = item.get("reference")
        if reference is None and item.get("reference_file") is not None:
            try:
                reference = _inside(directory, item["reference_file"]).read_text(
                    "utf-8"
                )
            except OSError as error:
                raise BenchmarkError(
                    "benchmark_manifest_invalid", "No se pudo leer una referencia."
                ) from error
        if reference is not None and not isinstance(reference, str):
            raise BenchmarkError("benchmark_manifest_invalid", "Referencia inválida.")
        items.append(BenchItem(audio, reference))
    return Dataset(directory.name, language, tuple(items))


def audio_duration_seconds(path: Path) -> float:
    """WAV via the stdlib; any other container via ``ffprobe``."""
    try:
        with wave.open(str(path), "rb") as handle:
            return handle.getnframes() / handle.getframerate()
    except (wave.Error, EOFError, OSError):
        pass
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        seconds = float(completed.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise BenchmarkError(
            "benchmark_audio_duration_unknown",
            "No se pudo medir la duración del audio.",
        ) from error
    if seconds <= 0:
        raise BenchmarkError("benchmark_audio_duration_unknown", "Duración inválida.")
    return seconds


# -- measurements -----------------------------------------------------------


def peak_rss_mib(*, children: bool = False) -> float:
    """Peak resident set of this process (or its finished children), in MiB."""
    who = resource.RUSAGE_CHILDREN if children else resource.RUSAGE_SELF
    return resource.getrusage(who).ru_maxrss / 1024  # Linux reports KiB


def read_vram_used_mib() -> int | None:
    """Used memory of the first GPU via ``nvidia-smi``; ``None`` if unavailable."""
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return int(completed.stdout.strip().splitlines()[0])
    except (OSError, subprocess.SubprocessError, IndexError, ValueError):
        return None


class VramSampler:
    """Polls GPU memory in a thread; the peak is a sampled lower bound."""

    def __init__(
        self,
        read: Callable[[], int | None] = read_vram_used_mib,
        interval: float = _VRAM_INTERVAL_SECONDS,
    ) -> None:
        self._read = read
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="voz-vram", daemon=True)
        self.baseline: int | None = None
        self.peak: int | None = None

    def __enter__(self) -> VramSampler:
        self.baseline = self.peak = self._read()
        if self.baseline is not None:
            self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join()
        self._sample()

    def _sample(self) -> None:
        used = self._read()
        if used is not None and (self.peak is None or used > self.peak):
            self.peak = used

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            self._sample()


def _silence_wav() -> io.BytesIO:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(bytes(2 * 16_000 * _WARMUP_SECONDS))
    buffer.seek(0)
    return buffer


def run_benchmark(
    *,
    provider: TranscriptionProvider,
    descriptor: ModelDescriptor,
    dataset: Dataset,
    language: str | None,
    device: str,
    compute_type: str,
    word_timestamps: bool = False,
    children_ram: bool = False,
    clock: Callable[[], float] = time.perf_counter,
    vram_read: Callable[[], int | None] = read_vram_used_mib,
    environment: dict[str, str] | None = None,
) -> BenchReport:
    """Warm up (model load), then time every clip and score it against its reference."""
    options = TranscriptionOptions(
        model=descriptor, language=language, word_timestamps=word_timestamps
    )
    # A short silent clip forces the lazy model load before any clip is timed.
    # ponytail: load_seconds includes one second of inference; whisper.cpp
    # reloads the model on every call, so there it is the per-call start-up cost.
    ram_before = peak_rss_mib(children=children_ram)
    with VramSampler(vram_read) as vram:
        started = clock()
        provider.transcribe(audio=_silence_wav(), options=options)
        load_seconds = clock() - started
        results: list[ItemResult] = []
        for item in dataset.items:
            seconds = audio_duration_seconds(item.audio)
            with item.audio.open("rb") as handle:
                started = clock()
                result = provider.transcribe(audio=handle, options=options)
                wall = clock() - started
            wer = cer = None
            if item.reference is not None:
                wer = word_error_rate(item.reference, result.text)
                cer = character_error_rate(item.reference, result.text)
            results.append(
                ItemResult(
                    audio=item.audio.name,
                    audio_seconds=seconds,
                    wall_seconds=wall,
                    rtf=wall / seconds,
                    wer=None if wer is None else wer.rate,
                    cer=None if cer is None else cer.rate,
                    word_edits=None if wer is None else wer.edits,
                    reference_words=None if wer is None else wer.reference_length,
                    char_edits=None if cer is None else cer.edits,
                    reference_chars=None if cer is None else cer.reference_length,
                )
            )
    ram_peak = peak_rss_mib(children=children_ram)
    audio_total = sum(r.audio_seconds for r in results)
    wall_total = sum(r.wall_seconds for r in results)
    return BenchReport(
        schema_version=SCHEMA_VERSION,
        engine=descriptor.provider_id,
        model_id=descriptor.model_id,
        source=descriptor.source,
        revision=descriptor.revision,
        device=device,
        compute_type=compute_type,
        language=language,
        dataset=dataset.name,
        load_seconds=load_seconds,
        totals=Totals(
            audio_seconds=audio_total,
            wall_seconds=wall_total,
            rtf=wall_total / audio_total,
            wer=_corpus_rate(results, "word_edits", "reference_words"),
            cer=_corpus_rate(results, "char_edits", "reference_chars"),
        ),
        memory=Memory(
            ram_peak_mib=ram_peak,
            ram_delta_mib=ram_peak - ram_before,
            vram_peak_mib=vram.peak if device == "cuda" else None,
            vram_baseline_mib=vram.baseline if device == "cuda" else None,
            vram_delta_mib=(
                vram.peak - vram.baseline
                if device == "cuda"
                and vram.peak is not None
                and vram.baseline is not None
                else None
            ),
        ),
        environment=environment or {},
        items=tuple(results),
    )


def _corpus_rate(results: list[ItemResult], edits: str, length: str) -> float | None:
    """Corpus-level rate: total edits over total reference length."""
    scored = [r for r in results if getattr(r, length) is not None]
    total = sum(getattr(r, length) for r in scored)
    if not scored or total == 0:
        return None
    return sum(getattr(r, edits) for r in scored) / total


# -- wiring -----------------------------------------------------------------


class _FixedModelDir:
    """Resolver that always answers with the explicit ``--model-dir``."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def resolve_path(self, descriptor: ModelDescriptor) -> Path:
        return self._directory


def find_descriptor(engine: str, source: str, revision: str) -> ModelDescriptor:
    """Match the pinned catalog so provenance is never made up.

    For whisper-cpp all models share one repo, so ``source`` is the model id
    (e.g. ``large-v3-turbo-q5_0``).
    """
    if engine == "faster-whisper":
        for entry in faster_whisper_catalog():
            if entry.descriptor.provenance == (source, revision):
                return entry.descriptor
    else:
        for entry in whisper_cpp_catalog():
            if (entry.descriptor.model_id, entry.descriptor.revision) == (
                source,
                revision,
            ):
                return entry.descriptor
    raise BenchmarkError(
        "benchmark_model_unknown",
        "source/revision no coinciden con ningún modelo del catálogo de VOZ.",
    )


def _version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "no instalado"


def describe_environment(engine: str) -> dict[str, str]:
    cpu = "desconocido"
    try:
        for line in Path("/proc/cpuinfo").read_text("utf-8", "replace").splitlines():
            if line.startswith("model name"):
                cpu = line.partition(":")[2].strip()
                break
    except OSError:
        pass
    gpu = read_gpu_memory()
    info = {
        "cpu": cpu,
        "gpu": "ninguna" if gpu is None else f"{gpu.name} ({gpu.total_mib} MiB)",
        "python": platform.python_version(),
        "sistema": f"{platform.system()} {platform.release()}",
    }
    if engine == "faster-whisper":
        info["faster-whisper"] = _version("faster-whisper")
        info["ctranslate2"] = _version("ctranslate2")
    return info


def build_provider(
    engine: str, model_dir: Path, *, device: str, compute_type: str
) -> TranscriptionProvider:
    resolver = _FixedModelDir(model_dir)
    if engine == "whisper-cpp":
        availability = probe_whisper_cpp()
        if not availability.available or availability.binary is None:
            raise BenchmarkError(
                "benchmark_engine_unavailable",
                "whisper-cli no disponible (VOZ_WHISPER_CPP_BIN o PATH).",
            )
        return WhisperCppProvider(
            binary=availability.binary,
            model_resolver=resolver,
            force_cpu=device == "cpu",
        )
    return FasterWhisperProvider(
        model_resolver=resolver,
        execution=ExecutionDecision(
            ComputeDevice(device), ComputePrecision(compute_type)
        ),
    )


def render_text(report: BenchReport) -> str:
    def pct(value: float | None) -> str:
        return "n/d" if value is None else f"{value * 100:.2f}%"

    lines = [
        f"Modelo: {report.engine}/{report.model_id} "
        f"({report.device} {report.compute_type})",
        f"Dataset: {report.dataset}  idioma: {report.language or 'auto'}",
        f"Carga (arranque): {report.load_seconds:.2f} s",
        "",
        f"{'audio':<28}{'dur s':>8}{'tiempo s':>10}{'RTF':>8}{'WER':>9}{'CER':>9}",
    ]
    lines += [
        f"{r.audio[:27]:<28}{r.audio_seconds:>8.1f}{r.wall_seconds:>10.2f}"
        f"{r.rtf:>8.3f}{pct(r.wer):>9}{pct(r.cer):>9}"
        for r in report.items
    ]
    t, m = report.totals, report.memory
    vram = (
        "n/d"
        if m.vram_peak_mib is None
        else f"{m.vram_peak_mib} MiB "
        f"(base {m.vram_baseline_mib}, delta {m.vram_delta_mib})"
    )
    lines += [
        "",
        f"TOTAL {t.audio_seconds:.1f} s de audio en {t.wall_seconds:.2f} s  "
        f"RTF {t.rtf:.3f}  WER {pct(t.wer)}  CER {pct(t.cer)}",
        f"RAM pico: {m.ram_peak_mib:.0f} MiB (delta {m.ram_delta_mib:.0f})  "
        f"VRAM pico: {vram}",
    ]
    return "\n".join(lines)


_COMPUTE_TYPE_OPTION = typer.Option(
    None,
    "--compute-type",
    help="float16|int8_float16|int8 (por defecto según device).",
)
_MODEL_DIR_OPTION = typer.Option(
    ..., "--model-dir", file_okay=False, help="Directorio local del modelo."
)
_LANGUAGE_OPTION = typer.Option(None, "--language", help="Anula el del manifest.")


def bench_command(
    model_dir: Path = _MODEL_DIR_OPTION,
    source: str = typer.Option(
        ...,
        "--source",
        help="Repo de origen (p. ej. Systran/faster-whisper-large-v3); "
        "con whisper-cpp, el id del modelo (large-v3-turbo-q5_0).",
    ),
    revision: str = typer.Option(..., "--revision", help="SHA de 40 caracteres."),
    dataset: str = typer.Option(
        ..., "--dataset", help="Nombre bajo $XDG_DATA_HOME/voz/benchmarks/ o ruta."
    ),
    device: str = typer.Option("cuda", "--device", help="cuda o cpu."),
    compute_type: str | None = _COMPUTE_TYPE_OPTION,
    engine: str = typer.Option(
        "faster-whisper", "--engine", help="faster-whisper o whisper-cpp."
    ),
    language: str | None = _LANGUAGE_OPTION,
    json_output: bool = typer.Option(False, "--json", help="Salida JSON."),
) -> None:
    """Mide tiempo, RTF, RAM/VRAM y WER/CER. Nunca descarga modelos."""
    try:
        if engine not in {"faster-whisper", "whisper-cpp"} or device not in {
            "cuda",
            "cpu",
        }:
            raise BenchmarkError(
                "benchmark_option_invalid", "engine o device inválido."
            )
        if engine == "whisper-cpp" and device != "cpu":
            raise BenchmarkError(
                "benchmark_option_invalid", "whisper-cpp solo se mide en cpu."
            )
        precision = compute_type or ("float16" if device == "cuda" else "int8")
        try:
            ComputePrecision(precision)
        except ValueError as error:
            raise BenchmarkError(
                "benchmark_option_invalid", "compute-type inválido."
            ) from error
        if not model_dir.is_dir():
            raise BenchmarkError("benchmark_model_not_found", "model-dir no existe.")
        benchmarks = resolve_voz_paths().data / "benchmarks"
        data = load_dataset(
            resolve_dataset_dir(
                dataset, benchmarks_dir=benchmarks, repo_root=checkout_root()
            )
        )
        descriptor = find_descriptor(engine, source, revision)
        provider = build_provider(
            engine, model_dir, device=device, compute_type=precision
        )
        report = run_benchmark(
            provider=provider,
            descriptor=descriptor,
            dataset=data,
            language=language or data.language,
            device=device,
            compute_type=precision,
            children_ram=engine == "whisper-cpp",
            environment=describe_environment(engine),
        )
    except BenchmarkError as error:
        typer.echo(f"{error.code}: {error}", err=True)
        raise typer.Exit(code=2) from error
    except TranscriptionError as error:
        typer.echo(f"{error.code.value}: {error.user_message}", err=True)
        raise typer.Exit(code=1) from error
    if json_output:
        typer.echo(json.dumps(dataclasses.asdict(report), ensure_ascii=False, indent=2))
    else:
        typer.echo(render_text(report))
