"""Fresh experiment bootstrap: constrain first, then import installed engines."""

from __future__ import annotations

import contextlib
import importlib.metadata
import json
import os
import platform
import signal
import sys
from dataclasses import asdict
from pathlib import Path

from voz.application.edge_lab import (
    MAX_DEFINITION_BYTES,
    ExperimentDefinition,
    LabError,
    ResourceProfile,
    decode_definition,
)


def apply_limits(profile: ResourceProfile) -> dict[str, object]:
    """Call only in a fresh worker, before native imports or thread creation."""
    if profile.systemd:
        raise LabError("lab_limit_unsupported")
    if profile.device != "cpu":
        raise LabError("lab_device_unavailable")
    effective: dict[str, object] = {
        "device": "cpu",
        "systemd": False,
        "thread_environment": {
            name: os.environ.get(name)
            for name in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        },
    }
    if profile.cpu_mask is not None:
        if not hasattr(os, "sched_setaffinity") or not hasattr(os, "sched_getaffinity"):
            raise LabError("lab_limit_unsupported")
        requested = set(profile.cpu_mask)
        try:
            if not requested <= os.sched_getaffinity(0):
                raise LabError("lab_limit_failed")
            os.sched_setaffinity(0, requested)
            if os.sched_getaffinity(0) != requested:
                raise LabError("lab_limit_failed")
        except OSError as error:
            raise LabError("lab_limit_failed") from error
    effective["cpu_mask"] = (
        sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None
    )
    if profile.address_space_bytes is not None:
        if not sys.platform.startswith("linux"):
            raise LabError("lab_limit_unsupported")
        import resource

        if not hasattr(resource, "RLIMIT_AS"):
            raise LabError("lab_limit_unsupported")
        try:
            _, hard = resource.getrlimit(resource.RLIMIT_AS)
            requested_memory = profile.address_space_bytes
            if hard != resource.RLIM_INFINITY and requested_memory > hard:
                raise LabError("lab_limit_failed")
            resource.setrlimit(resource.RLIMIT_AS, (requested_memory, requested_memory))
            if resource.getrlimit(resource.RLIMIT_AS) != (
                requested_memory,
                requested_memory,
            ):
                raise LabError("lab_limit_failed")
        except (OSError, ValueError) as error:
            raise LabError("lab_limit_failed") from error
    effective["address_space_bytes"] = None
    if sys.platform.startswith("linux"):
        import resource

        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        effective["address_space_bytes"] = {
            "soft": None if soft == resource.RLIM_INFINITY else soft,
            "hard": None if hard == resource.RLIM_INFINITY else hard,
        }
    return effective


def observe_host(engine: str) -> dict[str, object]:
    cpu = platform.processor() or None
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                cpu = line.partition(":")[2].strip()[:256]
                break
    except OSError:
        pass
    packages = {
        "faster-whisper": ("faster-whisper", "ctranslate2"),
        "whisper-cpp": (),
        "sherpa-onnx-tts": ("sherpa-onnx", "onnxruntime"),
    }[engine]
    versions: dict[str, object] = {"python": platform.python_version()}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    if engine == "whisper-cpp":
        versions["whisper-cli"] = None
    return {
        "cpu": cpu,
        "architecture": platform.machine(),
        "os": platform.system(),
        "os_release": platform.release(),
        "device": "cpu",
        "runtime_versions": versions,
        "compute_admission": "standalone; no cross-process compute lock",
        "external_contention": "not measured",
    }


def run_stt(
    definition: ExperimentDefinition,
) -> tuple[dict[str, object], dict[str, object]]:
    from voz.infrastructure.asr.catalog import faster_whisper_catalog
    from voz.infrastructure.asr.whisper_cpp_catalog import whisper_cpp_catalog
    from voz.infrastructure.constrained_process import outside_checkout
    from voz.infrastructure.paths import resolve_voz_paths
    from voz.interfaces.cli import bench

    directory = definition.model_directory
    if directory is None or not directory.is_dir():
        raise LabError("lab_model_unavailable")
    entries = (
        faster_whisper_catalog()
        if definition.engine == "faster-whisper"
        else whisper_cpp_catalog()
    )
    descriptor = next(
        (
            entry.descriptor
            for entry in entries
            if entry.descriptor.model_id == definition.model_id
        ),
        None,
    )
    if descriptor is None:
        raise LabError("lab_model_unavailable")
    data_root = outside_checkout(resolve_voz_paths().data)
    dataset_path = outside_checkout(definition.input_path)
    outside_checkout(directory)
    if not dataset_path.is_dir():
        raise LabError("lab_input_unavailable")
    # Preserve bench's dataset traversal and reference validation.
    bench.ensure_outside_checkout(
        data_root / "benchmarks", repo_root=bench.checkout_root()
    )
    try:
        dataset = bench.load_dataset(dataset_path)
    except bench.BenchmarkError as error:
        raise LabError("lab_input_unavailable") from error
    try:
        provider = bench.build_provider(
            definition.engine, directory, device="cpu", compute_type="int8"
        )
    except (ImportError, bench.BenchmarkError) as error:
        raise LabError("lab_runtime_unavailable") from error
    try:
        report = bench.run_benchmark(
            provider=provider,
            descriptor=descriptor,
            dataset=dataset,
            language=definition.language or dataset.language,
            device="cpu",
            compute_type="int8",
            children_ram=definition.engine == "whisper-cpp",
            vram_read=lambda: None,
        )
    finally:
        close = getattr(provider, "close", None)
        if callable(close):
            close()
    measured: dict[str, object] = {
        "bench_schema_version": report.schema_version,
        "load_seconds": report.load_seconds,
        "totals": asdict(report.totals),
        "memory": asdict(report.memory),
        "clips": len(report.items),
        "methods": {
            "load": "1 second silent inference plus model load",
            "ram": "largest completed child peak RSS"
            if definition.engine == "whisper-cpp"
            else "worker peak RSS",
            "vram": "unavailable on selected CPU; no GPU sampling",
        },
    }
    return measured, {
        "model": {
            "engine": descriptor.provider_id,
            "model_id": descriptor.model_id,
            "source": descriptor.source,
            "revision": descriptor.revision,
            "file_integrity": "directory supplied; files not rehashed",
        },
        "precision": "int8"
        if definition.engine == "faster-whisper"
        else "model-file quantization; bench compute_type is not applied",
        "language": definition.language or dataset.language,
    }


def run_tts(
    definition: ExperimentDefinition,
) -> tuple[dict[str, object], dict[str, object]]:
    from voz.infrastructure.edge_lab_tts import run_tts_benchmark

    return run_tts_benchmark(definition)


def _write(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        os.chmod(temporary, 0o600)
        json.dump(value, handle, allow_nan=False)
    temporary.replace(path)


def _cancel(_signum: int, _frame: object) -> None:
    raise LabError("lab_cancelled")


def main() -> int:
    if len(sys.argv) != 4:
        return 2
    request, ready, result = (Path(argument) for argument in sys.argv[1:])
    try:
        signal.signal(signal.SIGTERM, _cancel)
        with request.open("rb") as handle:
            definition = decode_definition(handle.read(MAX_DEFINITION_BYTES + 1))
        effective = apply_limits(definition.profile)
        observations = observe_host(definition.engine)
        _write(ready, {"effective": effective, "observations": observations})
        measured, extra = (
            run_stt(definition) if definition.workload == "stt" else run_tts(definition)
        )
        observations.update(extra)
        _write(
            result,
            {
                "status": "completed",
                "measured": measured,
                "estimated": {},
                "observations": observations,
            },
        )
        return 0
    except LabError as error:
        code = error.code
    except MemoryError:
        code = "lab_allocation_failed"
    except ImportError:
        code = "lab_runtime_unavailable"
    except Exception:
        code = "lab_worker_failed"
    with contextlib.suppress(OSError, MemoryError):
        _write(result, {"status": "failed", "code": code})
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
