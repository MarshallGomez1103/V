"""Supervise one fresh POSIX experiment tree without modifying the parent."""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path
from typing import cast

from voz.application.edge_lab import (
    MAX_RESULT_BYTES,
    ExperimentDefinition,
    ExperimentResult,
    LabCancellation,
    LabError,
    decode_definition,
    definition_payload,
)
from voz.infrastructure.paths import resolve_voz_paths

WORKER_MODULE = "voz.infrastructure.edge_lab_worker"
_POLL_SECONDS = 0.02
_GRACE_SECONDS = 0.3


def outside_checkout(path: Path) -> Path:
    """Resolve symlinks before enforcing the existing dataset privacy boundary."""
    try:
        resolved = path.expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise LabError("lab_storage_unsafe") from error
    root = Path(__file__).resolve().parents[3]
    if (root / "pyproject.toml").is_file() and resolved.is_relative_to(root):
        raise LabError("lab_storage_unsafe")
    return resolved


def _invalid_constant(_value: str) -> None:
    raise ValueError("Nonfinite JSON value")


def _read_object(path: Path) -> dict[str, object]:
    try:
        if not path.is_file():
            raise LabError("lab_invalid_result")
        with path.open("rb") as handle:
            content = handle.read(MAX_RESULT_BYTES + 1)
        if len(content) > MAX_RESULT_BYTES:
            raise LabError("lab_invalid_result")
        value: object = json.loads(content, parse_constant=_invalid_constant)
        if not isinstance(value, dict):
            raise LabError("lab_invalid_result")
        return cast(dict[str, object], value)
    except (OSError, ValueError, RecursionError) as error:
        raise LabError("lab_invalid_result") from error


def _stop_tree(child: subprocess.Popen[bytes]) -> None:
    # The worker owns its session; its descendants must not detach from it.
    grace_deadline = time.monotonic() + _GRACE_SECONDS
    with contextlib.suppress(ProcessLookupError):
        os.killpg(child.pid, signal.SIGTERM)
    with contextlib.suppress(subprocess.TimeoutExpired):
        child.wait(timeout=_GRACE_SECONDS)
    # Kill remaining descendants even if the leader already exited.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(child.pid, 0)
        time.sleep(max(0, grace_deadline - time.monotonic()))
        os.killpg(child.pid, signal.SIGKILL)
    try:
        child.wait(timeout=1.0)
    except subprocess.TimeoutExpired as error:
        raise LabError("lab_worker_failed") from error


class ConstrainedProcess:
    """Fixed worker argv; injected process factories are for trusted callers/tests."""

    def __init__(
        self,
        *,
        popen: Callable[..., subprocess.Popen[bytes]] | None = None,
        ready_timeout_seconds: float = 15.0,
    ) -> None:
        self._popen = popen or subprocess.Popen
        self._ready_timeout = ready_timeout_seconds

    def run(
        self,
        definition: ExperimentDefinition,
        cancellation: LabCancellation | None = None,
    ) -> ExperimentResult:
        constraints: dict[str, object] = {"requested": {}, "effective": {}}
        observations: dict[str, object] = {}
        try:
            # Revalidate even when a trusted caller constructed the DTO directly.
            definition = decode_definition(
                json.dumps(definition_payload(definition)).encode()
            )
            constraints["requested"] = asdict(definition.profile)
            if cancellation is not None and cancellation.is_cancelled():
                raise LabError("lab_cancelled")
            if os.name != "posix":
                raise LabError("lab_limit_unsupported")
            if definition.profile.systemd:
                # ponytail: enable scopes after controls/tree cleanup are verified.
                raise LabError("lab_limit_unsupported")
            if definition.profile.device != "cpu":
                raise LabError("lab_device_unavailable")
            definition = replace(
                definition,
                input_path=outside_checkout(definition.input_path),
                model_directory=outside_checkout(definition.model_directory)
                if definition.model_directory is not None
                else None,
            )
            cache = outside_checkout(resolve_voz_paths().cache / "edge-lab")
            cache.mkdir(mode=0o700, parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="run-", dir=cache) as directory:
                return self._run(
                    definition, cancellation, Path(directory), constraints, observations
                )
        except LabError as error:
            status = {"lab_cancelled": "cancelled", "lab_timeout": "timed_out"}.get(
                error.code, "failed"
            )
            return ExperimentResult(
                status, error.code, observations=observations, constraints=constraints
            )
        except KeyboardInterrupt:
            return ExperimentResult(
                "cancelled",
                "lab_cancelled",
                observations=observations,
                constraints=constraints,
            )
        except (OSError, ValueError, OverflowError):
            return ExperimentResult(
                "failed",
                "lab_worker_failed",
                observations=observations,
                constraints=constraints,
            )

    def _run(
        self,
        definition: ExperimentDefinition,
        cancellation: LabCancellation | None,
        directory: Path,
        constraints: dict[str, object],
        observations: dict[str, object],
    ) -> ExperimentResult:
        request = directory / "definition.json"
        ready = directory / "ready.json"
        result = directory / "result.json"
        with request.open("x", encoding="utf-8") as handle:
            os.chmod(request, 0o600)
            json.dump(definition_payload(definition), handle, allow_nan=False)
        environment = dict(os.environ)
        environment.update(
            {
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "CUDA_VISIBLE_DEVICES": "",
            }
        )
        for name in (
            "GOMP_CPU_AFFINITY",
            "OMP_PLACES",
            "OMP_PROC_BIND",
            "KMP_AFFINITY",
        ):
            environment.pop(name, None)
        threads = str(
            len(definition.profile.cpu_mask) if definition.profile.cpu_mask else 1
        )
        for name in (
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
        ):
            environment[name] = threads
        # -m must also work from the private working directory in a source checkout.
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
        started = time.monotonic()
        child = self._popen(
            [
                sys.executable,
                "-m",
                WORKER_MODULE,
                str(request),
                str(ready),
                str(result),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            start_new_session=True,
            cwd=directory,
            env=environment,
        )
        seen_ready = False
        try:
            while True:
                if cancellation is not None and cancellation.is_cancelled():
                    raise LabError("lab_cancelled")
                elapsed = time.monotonic() - started
                if elapsed >= definition.timeout_seconds or (
                    not seen_ready and elapsed >= self._ready_timeout
                ):
                    raise LabError("lab_timeout")
                if not seen_ready and ready.exists():
                    data = _read_object(ready)
                    if not isinstance(data.get("effective"), dict) or not isinstance(
                        data.get("observations"), dict
                    ):
                        raise LabError("lab_invalid_result")
                    constraints["effective"] = data["effective"]
                    observations.update(cast(dict[str, object], data["observations"]))
                    seen_ready = True
                returncode = child.poll()
                if returncode is not None:
                    break
                time.sleep(_POLL_SECONDS)
            data = _read_object(result)
            if data.get("status") == "failed" and isinstance(data.get("code"), str):
                raise LabError(cast(str, data["code"]))
            measured = data.get("measured")
            extra = data.get("observations")
            if (
                returncode != 0
                or not seen_ready
                or data.get("status") != "completed"
                or not isinstance(measured, dict)
                or not measured
                or not isinstance(extra, dict)
                or data.get("estimated") != {}
            ):
                raise LabError("lab_invalid_result")
            observations.update(cast(dict[str, object], extra))
            return ExperimentResult(
                "completed",
                measured=cast(dict[str, object], measured),
                observations=observations,
                constraints=constraints,
            )
        finally:
            _stop_tree(child)
