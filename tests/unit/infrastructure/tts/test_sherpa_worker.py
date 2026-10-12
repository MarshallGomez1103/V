"""sherpa-onnx TTS worker: in-process with a fake ``sherpa_onnx``, as a child for
error paths, and against a real model when ``VOZ_TTS_E2E_MODEL`` is set."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import time
import types
from pathlib import Path
from typing import Any

import pytest
from test_families import make_dir, write_model

from voz.application.ports.speech_synthesis import (
    PcmSampleFormat,
    SynthesisError,
    SynthesisFailureCode,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.infrastructure.tts import protocol, sherpa_worker
from voz.infrastructure.tts.protocol import WorkerRequest
from voz.infrastructure.tts.sherpa_provider import (
    MAX_CHUNK_CHARS,
    SHERPA_TTS_PROVIDER_ID,
    manifest_from_dir,
    sherpa_tts_info,
    sherpa_tts_provider,
)

Code = SynthesisFailureCode


class FakeSherpa:
    """Records the configs the worker builds; ``generate`` calls the callback."""

    def __init__(self, *, valid: bool = True, load_error: bool = False) -> None:
        self.built: dict[str, Any] = {}
        self.generated: dict[str, Any] = {}
        self.callback_results: list[int] = []
        self.module = types.ModuleType("sherpa_onnx")
        fake = self

        def family_class(name: str) -> Any:
            def build(**kwargs: Any) -> Any:
                fake.built[name] = kwargs
                return (name, kwargs)

            return build

        for name in (
            "OfflineTtsVitsModelConfig",
            "OfflineTtsKittenModelConfig",
            "OfflineTtsKokoroModelConfig",
            "OfflineTtsMatchaModelConfig",
        ):
            setattr(self.module, name, family_class(name))

        def model_config(**kwargs: Any) -> Any:
            fake.built["model"] = kwargs
            return kwargs

        class Config:
            def __init__(self, **kwargs: Any) -> None:
                fake.built["config"] = kwargs

            def validate(self) -> bool:
                return valid

        class Tts:
            num_speakers = 2

            def __init__(self, config: Any) -> None:
                if load_error:
                    raise RuntimeError("bad /secret/model.onnx")

            def generate(
                self, text: str, *, sid: int, speed: float, callback: Any
            ) -> Any:
                # Real 1.13.8 semantics: a callback returning 0 stops early.
                fake.generated = {"text": text, "sid": sid, "speed": speed}
                samples: list[float] = []
                for part, progress in (([0.0], 0.5), ([0.25, -0.5], 1.0)):
                    samples += part
                    fake.callback_results.append(callback(part, progress))
                    if not fake.callback_results[-1]:
                        break
                return types.SimpleNamespace(samples=samples, sample_rate=24000)

        self.module.OfflineTtsModelConfig = model_config  # type: ignore[attr-defined]
        self.module.OfflineTtsConfig = Config  # type: ignore[attr-defined]
        self.module.OfflineTts = Tts  # type: ignore[attr-defined]


def run_main(
    monkeypatch: pytest.MonkeyPatch, request: WorkerRequest | bytes
) -> list[protocol.WorkerEvent]:
    line = request if isinstance(request, bytes) else protocol.encode_request(request)
    out = io.BytesIO()
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(line)))
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(out, write_through=True))
    assert sherpa_worker.main() == 0
    out.seek(0)
    return list(protocol.read_events(out))


def kokoro_files(tmp_path: Path) -> dict[str, str]:
    root = make_dir(tmp_path, "voices.bin", "tokens.txt", "lexicon-us-en.txt")
    model = write_model(root, {"n_speakers": "2", "speaker_names": "af_heart,ef_dora"})
    return {
        "model": str(model),
        "voices": str(root / "voices.bin"),
        "tokens": str(root / "tokens.txt"),
        "lexicon_1": str(root / "lexicon-us-en.txt"),
    }


def req(
    files: dict[str, str], family: str = "kokoro", voice: str = "1"
) -> WorkerRequest:
    return WorkerRequest(family, files, voice, 1.25, "Hola mundo.", 3)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeSherpa:
    sherpa = FakeSherpa()
    monkeypatch.setitem(sys.modules, "sherpa_onnx", sherpa.module)
    return sherpa


def test_kokoro_request_builds_config_and_streams_float32(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake: FakeSherpa
) -> None:
    events = run_main(monkeypatch, req(kokoro_files(tmp_path), voice="ef_dora"))

    kokoro = fake.built["OfflineTtsKokoroModelConfig"]
    assert kokoro["lang"] == "es"
    assert kokoro["data_dir"].endswith("espeak-ng-data")
    assert "kokoro" in fake.built["model"]
    assert fake.built["model"]["num_threads"] == 3
    assert fake.built["model"]["provider"] == "cpu"
    assert fake.built["config"]["max_num_sentences"] == 1
    assert fake.generated == {"text": "Hola mundo.", "sid": 1, "speed": 1.25}
    assert fake.callback_results == [1, 1]
    progress = [e.fraction for e in events if isinstance(e, protocol.Progress)]
    assert progress == [0.5, 1.0]
    (audio,) = [e.audio for e in events if isinstance(e, protocol.AudioChunk)]
    assert audio.sample_format is PcmSampleFormat.FLOAT32
    assert audio.sample_rate == 24000
    assert audio.frame_count == 3
    assert isinstance(events[-1], protocol.End)


def test_unknown_voice_is_voice_not_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake: FakeSherpa
) -> None:
    files = kokoro_files(tmp_path)

    for voice in ("nobody", "2"):
        (event,) = run_main(monkeypatch, req(files, voice=voice))
        assert event == protocol.WorkerError("voice_not_found", "unknown voice")


def test_sid_beyond_the_loaded_model_is_voice_not_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake: FakeSherpa
) -> None:
    root = make_dir(tmp_path, "tokens.txt")
    model = write_model(root, {"n_speakers": "5"})  # metadata lies: runtime has 2
    files = {"model": str(model), "tokens": str(root / "tokens.txt")}

    (event,) = run_main(monkeypatch, req(files, family="vits", voice="4"))

    assert isinstance(event, protocol.WorkerError)
    assert event.code == "voice_not_found"


@pytest.mark.parametrize(
    ("sherpa", "expected"),
    [
        (FakeSherpa(valid=False), "model_not_installed"),
        (FakeSherpa(load_error=True), "model_not_installed"),
    ],
)
def test_invalid_or_unloadable_model_is_model_not_installed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sherpa: FakeSherpa, expected: str
) -> None:
    monkeypatch.setitem(sys.modules, "sherpa_onnx", sherpa.module)

    (event,) = run_main(monkeypatch, req(kokoro_files(tmp_path)))

    assert isinstance(event, protocol.WorkerError)
    assert event.code == expected
    assert "/secret" not in event.message


def test_missing_files_and_unknown_family_are_model_not_installed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake: FakeSherpa
) -> None:
    files = kokoro_files(tmp_path)
    no_voices = {k: v for k, v in files.items() if k != "voices"}

    for request in (
        req(no_voices),
        req(files, family="zipvoice"),
        req({"model": str(tmp_path / "gone.onnx")}),
    ):
        (event,) = run_main(monkeypatch, request)
        assert isinstance(event, protocol.WorkerError)
        assert event.code == "model_not_installed"
        assert str(tmp_path) not in event.message


def test_missing_runtime_is_runtime_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setitem(sys.modules, "sherpa_onnx", None)  # import raises

    (event,) = run_main(monkeypatch, req(kokoro_files(tmp_path)))

    assert isinstance(event, protocol.WorkerError)
    assert event.code == "runtime_unavailable"


def test_bad_request_and_generation_errors_are_synthesis_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake: FakeSherpa
) -> None:
    def explode(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("native failure at /home/x/model.onnx")

    (bad,) = run_main(monkeypatch, b"not json\n")
    monkeypatch.setattr(fake.module.OfflineTts, "generate", explode)
    (failed,) = run_main(monkeypatch, req(kokoro_files(tmp_path)))

    for event in (bad, failed):
        assert isinstance(event, protocol.WorkerError)
        assert event.code == "synthesis_failed"
        assert "/home" not in event.message


def test_broken_stdout_stops_generation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake: FakeSherpa
) -> None:
    class Closed(io.RawIOBase):
        def writable(self) -> bool:
            return True

        def write(self, _data: Any) -> int:
            raise BrokenPipeError

    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(io.BufferedWriter(Closed())))

    sherpa_worker._render(req(kokoro_files(tmp_path)))  # pyright: ignore[reportPrivateUsage]

    assert fake.callback_results == [0]


def test_child_process_reports_typed_error_and_exits_zero(tmp_path: Path) -> None:
    request = protocol.encode_request(req({"model": str(tmp_path / "gone.onnx")}))

    child = subprocess.run(
        [sys.executable, "-m", "voz.infrastructure.tts.sherpa_worker"],
        input=request,
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert child.returncode == 0
    assert child.stdout.startswith(b"V ERR model_not_installed")
    assert str(tmp_path).encode() not in child.stdout


def test_provider_factory_declares_the_engine() -> None:
    info = sherpa_tts_info()
    provider = sherpa_tts_provider({})

    assert provider.describe() == info
    assert info.provider_id == SHERPA_TTS_PROVIDER_ID == "sherpa-onnx-tts"
    assert info.max_chunk_chars == MAX_CHUNK_CHARS
    assert info.locality.value == "local"
    assert info.streaming is False
    provider.close()


def test_manifest_from_dir_reads_files_and_voices(tmp_path: Path) -> None:
    root = make_dir(tmp_path, "tokens.txt")
    write_model(root, {"n_speakers": "1"}, name="es_MX-ald-medium.onnx")

    manifest = manifest_from_dir("piper", root, languages=("es",))

    assert manifest.family == "vits"
    assert [v.id for v in manifest.voices] == ["0"]
    assert manifest.disk_bytes and manifest.disk_bytes > 0


# --- real model, opt-in ---------------------------------------------------------

E2E_MODEL = os.environ.get("VOZ_TTS_E2E_MODEL")
E2E_FAMILY = os.environ.get("VOZ_TTS_E2E_FAMILY", "vits")


@pytest.mark.skipif(not E2E_MODEL, reason="set VOZ_TTS_E2E_MODEL to a model dir")
def test_real_model_renders_audio_with_progress_and_cancels() -> None:
    assert E2E_MODEL
    manifest = manifest_from_dir(E2E_FAMILY, Path(E2E_MODEL), languages=("es",))
    provider = sherpa_tts_provider({"e2e": manifest})
    model = ModelDescriptor(
        provider_id=SHERPA_TTS_PROVIDER_ID,
        model_id="e2e",
        display_name="E2E",
        capabilities=frozenset({ModelCapability.SYNTHESIS}),
    )
    text = (
        "Hola, esta es una prueba del motor de voz local. "
        "La segunda oración sirve para medir el progreso por frases. "
        "Y una tercera, para que el audio dure varios segundos."
    )
    progress: list[float] = []
    try:
        started = time.monotonic()
        audio = provider.synthesize(
            text,
            model=model,
            voice_id=manifest.voices[0].id,
            on_progress=progress.append,
        )
        elapsed = time.monotonic() - started
        print(
            f"\nE2E {E2E_FAMILY}: {audio.duration_seconds:.2f}s audio in "
            f"{elapsed:.2f}s (RTF incl. load {elapsed / audio.duration_seconds:.3f})"
        )
        assert audio.sample_format is PcmSampleFormat.FLOAT32
        assert audio.duration_seconds > 6  # all three sentences, not just one
        assert len(progress) >= 2 and progress[-1] == 1.0

        class Soon:
            def __init__(self) -> None:
                self.at = time.monotonic() + 0.3

            def is_cancelled(self) -> bool:
                return time.monotonic() >= self.at

        with pytest.raises(SynthesisError) as raised:
            provider.synthesize(
                text, model=model, voice_id=manifest.voices[0].id, cancellation=Soon()
            )
        assert raised.value.code is Code.CANCELLED
    finally:
        provider.close()
