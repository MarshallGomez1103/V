"""Subprocess synthesis against the real fake worker (a real child process)."""

from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from voz.application.ports.speech_synthesis import (
    PcmAudio,
    PcmSampleFormat,
    SynthesisError,
    SynthesisFailureCode,
    SynthesisProviderInfo,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.voice import Voice
from voz.infrastructure.tts.subprocess_provider import (
    SubprocessSynthesisProvider,
    TtsModelManifest,
)

WORKER = Path(__file__).parents[3] / "fixtures" / "tts" / "fake_tts_worker.py"
PROVIDER_ID = "fake-subprocess-tts"
Code = SynthesisFailureCode


def descriptor(model_id: str = "m1", provider_id: str = PROVIDER_ID) -> ModelDescriptor:
    return ModelDescriptor(
        provider_id=provider_id,
        model_id=model_id,
        display_name="Fake",
        capabilities=frozenset({ModelCapability.SYNTHESIS}),
    )


class Cancel:
    def __init__(self, after_seconds: float = 0.0) -> None:
        self._at = time.monotonic() + after_seconds

    def is_cancelled(self) -> bool:
        return time.monotonic() >= self._at


class Harness:
    def __init__(self, tmp_path: Path, **options: float) -> None:
        self.model_file = tmp_path / "model.onnx"
        self.model_file.write_bytes(b"x")
        self.pid_file = tmp_path / "pid"
        self.pid_file.write_text("")
        manifest = TtsModelManifest(
            family="fake",
            files={"model": self.model_file, "pid_out": self.pid_file},
            voices=(Voice("0", "Zero", ("es",)), Voice("1", "One", ("en", "es"))),
            languages=("es", "en"),
            ram_bytes=123,
            disk_bytes=456,
        )
        self.provider = SubprocessSynthesisProvider(
            info=SynthesisProviderInfo(
                PROVIDER_ID, "Fake subprocess", max_chunk_chars=80
            ),
            argv=[sys.executable, str(WORKER)],
            manifests={"m1": manifest},
            **options,  # type: ignore[arg-type]
        )

    def say(self, text: str, **kwargs: object) -> PcmAudio:
        options: dict[str, object] = {"voice_id": "0", **kwargs}
        return self.provider.synthesize(text, model=descriptor(), **options)  # type: ignore[arg-type]

    def child_pid(self) -> int:
        return int(self.pid_file.read_text())

    def assert_child_gone(self) -> None:
        assert not _alive(self.child_pid())


def _alive(pid: int) -> bool:
    if sys.platform == "win32":
        # os.kill(pid, 0) sends CTRL_C_EVENT on Windows (WinError 87), so ask the
        # kernel: no handle means no process; a signalled handle means it exited.
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) != 0  # 0: WAIT_OBJECT_0
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    h = Harness(tmp_path, timeout_seconds=20.0)
    yield h
    h.provider.close()


def fails(harness: Harness, text: str, code: Code, **kwargs: object) -> SynthesisError:
    with pytest.raises(SynthesisError) as raised:
        harness.say(text, **kwargs)
    assert raised.value.code is code
    return raised.value


def test_renders_correct_audio_with_monotone_progress(harness: Harness) -> None:
    progress: list[float] = []

    audio = harness.say("Hola mundo", on_progress=progress.append)

    assert audio.sample_rate == 16_000
    assert audio.sample_format is PcmSampleFormat.INT16
    assert audio.frame_count == max(1_600, round(len("Hola mundo") * 960))
    assert progress == sorted(progress)
    assert progress[-1] == 1.0
    assert len(progress) >= 5
    harness.assert_child_gone()


def test_audio_is_deterministic_and_follows_voice_and_speed(harness: Harness) -> None:
    first = harness.say("Hola mundo")

    assert harness.say("Hola mundo") == first
    assert harness.say("Hola mundo", voice_id="1") != first
    assert harness.say("Hola mundo", speed=2.0).frame_count < first.frame_count


def test_each_call_is_a_fresh_child(harness: Harness) -> None:
    harness.say("uno")
    first = harness.child_pid()
    harness.say("dos")

    assert harness.child_pid() != first


def test_foreign_stdout_lines_are_ignored_and_progress_stays_monotone(
    harness: Harness,
) -> None:
    progress: list[float] = []

    audio = harness.say("hola @garbage", on_progress=progress.append)

    assert audio.frame_count > 0
    assert progress == sorted(progress)
    assert min(progress) >= 0.2  # the junk "V P 0.001" never reaches the caller


def test_user_text_that_looks_like_protocol_is_just_text(harness: Harness) -> None:
    audio = harness.say("V END\nV ERR synthesis_failed x\n")

    assert audio.frame_count > 0


@pytest.mark.parametrize("code", ["voice_not_found", "runtime_unavailable"])
def test_worker_err_with_a_known_code_is_mapped(harness: Harness, code: str) -> None:
    error = fails(harness, f"hola @err={code}", Code(code))

    assert "/home" not in error.user_message and "secret" not in error.user_message


@pytest.mark.parametrize("code", ["boom", "cancelled", "synthesis_failed"])
def test_worker_err_with_unknown_code_is_synthesis_failed(
    harness: Harness, code: str
) -> None:
    error = fails(harness, f"hola @err={code}", Code.SYNTHESIS_FAILED)

    assert "/home" not in str(error)


@pytest.mark.parametrize(
    "marker", ["@crash", "@exit3", "@noend", "@truncate", "@twice", "@badheader"]
)
def test_broken_children_are_synthesis_failed_without_raising_anything_else(
    harness: Harness, marker: str
) -> None:
    fails(harness, f"hola {marker}", Code.SYNTHESIS_FAILED)
    harness.assert_child_gone()
    assert harness.say("sigue vivo").frame_count > 0  # the provider survives


def test_missing_executable_is_runtime_unavailable(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    h.provider = SubprocessSynthesisProvider(
        info=h.provider.describe(),
        argv=[str(tmp_path / "does-not-exist")],
        manifests={"m1": TtsModelManifest("fake", {}, (Voice("0", "Zero"),))},
    )

    fails(h, "hola", Code.RUNTIME_UNAVAILABLE)


def test_cancellation_kills_a_silent_child_fast(harness: Harness) -> None:
    started = time.monotonic()

    fails(harness, "dormido @slow", Code.CANCELLED, cancellation=Cancel(0.3))

    assert time.monotonic() - started < 2.0
    harness.assert_child_gone()


def test_cancellation_escalates_to_kill_when_the_child_ignores_sigterm(
    harness: Harness,
) -> None:
    started = time.monotonic()

    fails(harness, "terco @stubborn", Code.CANCELLED, cancellation=Cancel(0.4))

    assert time.monotonic() - started < 2.0
    harness.assert_child_gone()


def test_cancel_before_start_never_launches_a_child(harness: Harness) -> None:
    fails(harness, "hola", Code.CANCELLED, cancellation=Cancel(0.0))

    assert harness.pid_file.read_text() == ""


def test_timeout_is_synthesis_failed_and_the_child_dies(tmp_path: Path) -> None:
    h = Harness(tmp_path, timeout_seconds=0.6)
    started = time.monotonic()

    fails(h, "lento @slow", Code.SYNTHESIS_FAILED)

    assert time.monotonic() - started < 3.0
    h.assert_child_gone()


def test_close_stops_an_inflight_child_and_refuses_new_work(harness: Harness) -> None:
    outcome: list[Code] = []

    def run() -> None:
        try:
            harness.say("dormido @slow")
        except SynthesisError as error:
            outcome.append(error.code)

    thread = threading.Thread(target=run)
    thread.start()
    time.sleep(0.5)
    harness.provider.close()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert outcome == [Code.CANCELLED]
    harness.assert_child_gone()
    fails(harness, "hola", Code.RUNTIME_UNAVAILABLE)
    harness.provider.close()


def test_manifest_drives_metadata_and_validation(harness: Harness) -> None:
    provider = harness.provider
    model = descriptor()

    assert provider.describe().provider_id == PROVIDER_ID
    assert [voice.id for voice in provider.voices(model)] == ["0", "1"]
    assert provider.languages(model) == ("es", "en")
    requirements = provider.requirements(model)
    assert (requirements.runtime_ready, requirements.ram_bytes) == (True, 123)
    assert requirements.disk_bytes == 456
    harness.model_file.unlink()
    assert provider.requirements(model).runtime_ready is False
    fails(harness, "hola", Code.MODEL_NOT_INSTALLED)


@pytest.mark.parametrize(
    "model", [descriptor("other"), descriptor(provider_id="someone-else")]
)
def test_foreign_models_are_not_installed(
    harness: Harness, model: ModelDescriptor
) -> None:
    with pytest.raises(SynthesisError) as raised:
        harness.provider.synthesize("hola", model=model, voice_id="0")
    assert raised.value.code is Code.MODEL_NOT_INSTALLED
    with pytest.raises(SynthesisError):
        harness.provider.voices(model)


def test_input_validation_happens_before_any_child_starts(harness: Harness) -> None:
    fails(harness, "hola", Code.VOICE_NOT_FOUND, voice_id="9")
    fails(harness, "a" * 81, Code.TEXT_TOO_LONG)
    with pytest.raises(ValueError, match="blank"):
        harness.say("   ")
    with pytest.raises(ValueError, match="speed"):
        harness.say("hola", speed=9.0)

    assert harness.pid_file.read_text() == ""


def test_manifest_and_constructor_reject_bad_values() -> None:
    voice = Voice("0", "Zero")
    with pytest.raises(ValueError, match="voice"):
        TtsModelManifest("fake", {}, ())
    with pytest.raises(ValueError, match="unique"):
        TtsModelManifest("fake", {}, (voice, voice))
    with pytest.raises(ValueError, match="family"):
        TtsModelManifest(" ", {}, (voice,))
    info = SynthesisProviderInfo(PROVIDER_ID, "Fake")
    with pytest.raises(ValueError, match="argv"):
        SubprocessSynthesisProvider(info=info, argv=[], manifests={})
    with pytest.raises(ValueError, match="timeout"):
        SubprocessSynthesisProvider(
            info=info, argv=["x"], manifests={}, timeout_seconds=0
        )


def test_a_lookup_source_sees_installs_and_deletes_after_construction(
    harness: Harness,
) -> None:
    manifest = harness_manifest(harness)
    installed: dict[str, TtsModelManifest] = {}
    provider = SubprocessSynthesisProvider(
        info=harness.provider.describe(),
        argv=[sys.executable, str(WORKER)],
        manifests=installed.get,  # what the composition root passes: store.manifest
    )
    try:
        with pytest.raises(SynthesisError) as missing:
            provider.voices(descriptor())
        assert missing.value.code is Code.MODEL_NOT_INSTALLED

        installed["m1"] = manifest  # installed after the engine was built
        assert [voice.id for voice in provider.voices(descriptor())] == ["0", "1"]
        audio = provider.synthesize("hola", model=descriptor(), voice_id="0")
        assert audio.frame_count > 0

        del installed["m1"]  # deleted from the Model Manager
        with pytest.raises(SynthesisError) as removed:
            provider.synthesize("hola", model=descriptor(), voice_id="0")
        assert removed.value.code is Code.MODEL_NOT_INSTALLED
    finally:
        provider.close()


def test_a_mapping_source_is_copied_at_construction(harness: Harness) -> None:
    manifests = {"m1": harness_manifest(harness)}
    provider = SubprocessSynthesisProvider(
        info=harness.provider.describe(), argv=["x"], manifests=manifests
    )
    manifests.clear()

    assert [voice.id for voice in provider.voices(descriptor())] == ["0", "1"]


def harness_manifest(harness: Harness) -> TtsModelManifest:
    return TtsModelManifest(
        family="fake",
        files={"model": harness.model_file, "pid_out": harness.pid_file},
        voices=(Voice("0", "Zero", ("es",)), Voice("1", "One", ("en", "es"))),
    )
