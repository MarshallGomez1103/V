"""Trusted child entry point for loading custom weights with installed engines."""

from __future__ import annotations

import contextlib
import importlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import wave
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from voz.application.ports.custom_models import CustomModelError, CustomValidation
from voz.application.ports.model_installation import CancelCheck
from voz.domain.entities.voice import Voice
from voz.infrastructure.asr.sherpa_onnx_worker import load_whisper
from voz.infrastructure.asr.whisper_cpp import locate_whisper_cli
from voz.infrastructure.audio.media_args import NO_WINDOW
from voz.infrastructure.custom_models import model_files
from voz.infrastructure.tts.model_store import validate_custom_tts_load


class SubprocessModelValidator:
    def __init__(
        self, *, argv: Sequence[str] | None = None, timeout_seconds: float = 120.0
    ) -> None:
        self._argv = tuple(argv or (sys.executable, "-m", __name__))
        self._timeout = timeout_seconds

    def validate(
        self,
        directory: Path,
        engine: str,
        family: str,
        *,
        file_roles: dict[str, str],
        cancelled: CancelCheck,
    ) -> CustomValidation:
        if os.name == "nt" and engine == "whisper-cpp":
            raise CustomModelError(
                "custom_model_runtime_unavailable",
                "Isolated whisper.cpp validation is not available on this platform.",
            )
        if cancelled():
            raise CustomModelError(
                "model_installation_cancelled", "The import was cancelled."
            )
        with tempfile.TemporaryFile() as output:
            try:
                child = subprocess.Popen(
                    [
                        *self._argv,
                        engine,
                        family,
                        str(directory),
                        json.dumps(file_roles),
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                    start_new_session=os.name != "nt",
                    creationflags=NO_WINDOW,
                    env={
                        **os.environ,
                        "HF_HUB_OFFLINE": "1",
                        "TRANSFORMERS_OFFLINE": "1",
                        "HF_DATASETS_OFFLINE": "1",
                    },
                )
            except OSError:
                raise CustomModelError(
                    "custom_model_runtime_unavailable",
                    "The model validator could not be started.",
                ) from None
            deadline = time.monotonic() + self._timeout
            try:
                while child.poll() is None:
                    if cancelled():
                        raise CustomModelError(
                            "model_installation_cancelled", "The import was cancelled."
                        )
                    if time.monotonic() >= deadline:
                        raise CustomModelError(
                            "custom_model_validation_timeout",
                            "The model validation did not finish in time.",
                        )
                    with contextlib.suppress(subprocess.TimeoutExpired):
                        child.wait(timeout=0.05)
                if child.returncode != 0:
                    raise CustomModelError(
                        "custom_model_validation_failed",
                        "The selected engine could not load the model.",
                    )
                output.seek(0)
                raw = output.read(65_537)
                if len(raw) > 65_536:
                    raise ValueError("validator output too large")
                document = json.loads(raw)
                voices = tuple(
                    Voice(v["id"], v["name"], tuple(v["languages"]))
                    for v in document["voices"]
                )
                if engine == "sherpa-onnx-tts" and not voices:
                    raise ValueError("missing voices")
                return CustomValidation(voices, tuple(document["languages"]))
            except (OSError, ValueError, TypeError, KeyError):
                raise CustomModelError(
                    "custom_model_validation_failed",
                    "The selected engine could not load the model.",
                ) from None
            finally:
                if os.name != "nt":
                    # This process group belongs only to this validation. Kill
                    # remaining descendants even if their parent already exited.
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(child.pid, signal.SIGKILL)
                elif child.poll() is None:
                    with contextlib.suppress(ProcessLookupError):
                        child.kill()
                if child.poll() is None:
                    child.wait(timeout=5)


def _load(
    directory: Path, engine: str, family: str, roles: dict[str, str]
) -> CustomValidation:
    if engine == "sherpa-onnx-asr" and family == "whisper":
        load_whisper(model_files(directory, family, roles))
        return CustomValidation()
    if engine == "faster-whisper" and family == "ctranslate2":
        module: Any = importlib.import_module("faster_whisper")
        module.WhisperModel(
            str(directory),
            device="cpu",
            compute_type="int8",
            local_files_only=True,
            cpu_threads=1,
            num_workers=1,
        )
        return CustomValidation()
    if engine == "sherpa-onnx-tts":
        return validate_custom_tts_load(family, model_files(directory, family, roles))
    if engine == "whisper-cpp" and family == "ggml":
        binary = locate_whisper_cli()
        models = list(directory.glob("ggml-*.bin"))
        if binary is None or len(models) != 1:
            raise ValueError("missing runtime or weights")
        with tempfile.TemporaryDirectory(prefix="voz-model-probe-") as temporary:
            audio = Path(temporary) / "silence.wav"
            with wave.open(str(audio), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\0" * 32000)
            result = subprocess.run(
                [str(binary), "-m", str(models[0]), "-f", str(audio), "--no-gpu"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=110,
                creationflags=NO_WINDOW,
            )
            if result.returncode:
                raise ValueError("cannot load model")
        return CustomValidation()
    raise ValueError("unsupported engine")


def main() -> int:
    # Native loaders can print paths. Suppress both streams during load, then
    # write only the small, path-free JSON result through a saved descriptor.
    result_fd = os.dup(sys.stdout.fileno())
    try:
        with open(os.devnull, "wb") as sink:
            os.dup2(sink.fileno(), sys.stdout.fileno())
            os.dup2(sink.fileno(), sys.stderr.fileno())
            engine, family, directory, roles = sys.argv[1:]
            result = _load(Path(directory), engine, family, json.loads(roles))
        os.write(result_fd, json.dumps(asdict(result)).encode())
        return 0
    except Exception:
        return 1
    finally:
        os.close(result_fd)


if __name__ == "__main__":
    os._exit(main())
