"""whisper.cpp adapter against a fake ``whisper-cli`` script (no real binary)."""

import json
import os
import stat
import sys
import threading
from io import BytesIO
from pathlib import Path

import pytest

from voz.application.ports.transcription import (
    TranscriptionClip,
    TranscriptionError,
    TranscriptionFailureCode,
    TranscriptionOptions,
    TranscriptionResult,
)
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.infrastructure.asr.whisper_cpp import (
    WhisperCppProvider,
    WhisperCppUnavailableReason,
    locate_whisper_cli,
    probe_whisper_cpp,
)

_FAKE = Path(__file__).parents[3] / "fixtures/whisper_cpp/fake_whisper_cli.py"
_WAV = Path(__file__).parents[3] / "fixtures/media/synthetic-tone.wav"
_DESCRIPTOR = ModelDescriptor(
    provider_id="whisper-cpp",
    model_id="base",
    display_name="whisper.cpp base",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    source="example/whisper-cpp-fixture",
    revision="e" * 40,
)
_CODE = TranscriptionFailureCode


class _Resolver:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def resolve_path(self, descriptor: ModelDescriptor) -> Path:
        assert descriptor is _DESCRIPTOR
        return self.directory


class _Cancel:
    def __init__(self, condition: "threading.Event | Path | None" = None) -> None:
        self.condition = condition

    def is_cancelled(self) -> bool:
        if isinstance(self.condition, Path):
            return self.condition.exists()
        return self.condition is not None and self.condition.is_set()


def install_fake_cli(directory: Path) -> Path:
    binary = directory / "whisper-cli"
    binary.write_text(f"#!{sys.executable}\n{_FAKE.read_text()}", encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in ("MODE", "PAYLOAD", "HELP", "PID", "LOG"):
        monkeypatch.delenv(f"FAKE_WCPP_{name}", raising=False)
    (tmp_path / "bin").mkdir()
    return install_fake_cli(tmp_path / "bin")


@pytest.fixture
def models(tmp_path: Path) -> _Resolver:
    directory = tmp_path / "model"
    directory.mkdir()
    (directory / "ggml-base.bin").write_bytes(b"ggml")
    return _Resolver(directory)


def _provider(
    cli: Path, models: _Resolver, tmp_path: Path, *, force_cpu: bool = False
) -> WhisperCppProvider:
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    return WhisperCppProvider(
        binary=cli,
        model_resolver=models,
        force_cpu=force_cpu,
        temp_root=work,
        poll_seconds=0.02,
    )


def _transcribe(
    provider: WhisperCppProvider,
    *,
    language: str | None = None,
    clip: TranscriptionClip | None = None,
    word_timestamps: bool = True,
) -> TranscriptionResult:
    with _WAV.open("rb") as audio:
        return provider.transcribe(
            audio=audio,
            options=TranscriptionOptions(
                model=_DESCRIPTOR,
                language=language,
                clip=clip,
                word_timestamps=word_timestamps,
            ),
        )


def _payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: object) -> None:
    path = tmp_path / "payload.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setenv("FAKE_WCPP_PAYLOAD", str(path))


# --- S9.02 detection ---------------------------------------------------------


def test_probe_accepts_a_valid_executable_and_reads_its_version(cli: Path) -> None:
    availability = probe_whisper_cpp(env={"VOZ_WHISPER_CPP_BIN": str(cli)})

    assert availability.available
    assert availability.version == "1.7.4"
    assert availability.reason is None
    assert availability.binary == cli


def test_probe_finds_whisper_cli_on_path(cli: Path) -> None:
    assert locate_whisper_cli({"PATH": str(cli.parent)}) == cli
    assert probe_whisper_cpp(env={"PATH": str(cli.parent)}).available


def test_probe_reports_not_found_without_env_or_path(tmp_path: Path) -> None:
    result = probe_whisper_cpp(env={"PATH": str(tmp_path)})

    assert not result.available
    assert result.reason is WhisperCppUnavailableReason.NOT_FOUND


def test_explicit_env_var_is_not_replaced_by_path(cli: Path, tmp_path: Path) -> None:
    env = {"VOZ_WHISPER_CPP_BIN": str(tmp_path / "missing"), "PATH": str(cli.parent)}

    assert probe_whisper_cpp(env=env).reason is WhisperCppUnavailableReason.NOT_FOUND


def test_probe_rejects_old_or_foreign_executables(
    cli: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_WCPP_HELP", "old")

    result = probe_whisper_cpp(env={"VOZ_WHISPER_CPP_BIN": str(cli)})

    assert not result.available
    assert result.reason is WhisperCppUnavailableReason.MISSING_FLAGS


def test_probe_reports_a_non_launchable_file(tmp_path: Path) -> None:
    broken = tmp_path / "whisper-cli"
    broken.write_text("#!/nonexistent/interpreter\n", encoding="utf-8")
    broken.chmod(0o755)

    result = probe_whisper_cpp(env={"VOZ_WHISPER_CPP_BIN": str(broken)})

    assert result.reason is WhisperCppUnavailableReason.NOT_EXECUTABLE


def test_probe_times_out_on_a_hanging_help(tmp_path: Path) -> None:
    hang = tmp_path / "whisper-cli"
    hang.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(30)\n")
    hang.chmod(0o755)

    result = probe_whisper_cpp(
        env={"VOZ_WHISPER_CPP_BIN": str(hang)}, timeout_seconds=0.3
    )

    assert result.reason is WhisperCppUnavailableReason.PROBE_TIMEOUT


# --- S9.01/S9.06 transcription ----------------------------------------------


def test_transcribes_through_the_cli_and_maps_canonical_segments(
    cli: Path, models: _Resolver, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("FAKE_WCPP_LOG", str(log))

    result = _transcribe(_provider(cli, models, tmp_path), language="es-CO")

    assert result.text == "hola mundo"
    assert result.language == "es"
    assert [(s.start_ms, s.end_ms) for s in result.segments] == [(0, 100), (100, 250)]
    argv = json.loads(log.read_text().splitlines()[0])["argv"]
    assert argv[argv.index("--language") + 1] == "es"
    assert argv[argv.index("--model") + 1].endswith("ggml-base.bin")
    assert "--output-json-full" in argv
    assert "--no-gpu" not in argv
    assert "--offset-t" not in argv


def test_language_none_means_auto_and_clip_and_cpu_flags_are_forwarded(
    cli: Path, models: _Resolver, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("FAKE_WCPP_LOG", str(log))

    _transcribe(
        _provider(cli, models, tmp_path, force_cpu=True),
        clip=TranscriptionClip(1_000, 3_500),
    )

    argv = json.loads(log.read_text().splitlines()[0])["argv"]
    assert argv[argv.index("--language") + 1] == "auto"
    assert "--no-gpu" in argv
    assert argv[argv.index("--offset-t") + 1] == "1000"
    assert argv[argv.index("--duration") + 1] == "2500"


def test_temporary_directory_is_private_and_removed(
    cli: Path, models: _Resolver, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("FAKE_WCPP_LOG", str(log))
    work = tmp_path / "work"

    _transcribe(_provider(cli, models, tmp_path))

    cwd = Path(json.loads(log.read_text().splitlines()[0])["cwd"])
    assert cwd.parent == work
    assert not cwd.exists()
    assert list(work.iterdir()) == []


def test_empty_and_overlapping_segments_are_normalized(
    cli: Path, models: _Resolver, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _payload(
        tmp_path,
        monkeypatch,
        {
            "transcription": [
                {"offsets": {"from": 0, "to": 100}, "text": "  hola  "},
                {"offsets": {"from": 100, "to": 120}, "text": "   "},
                {"offsets": {"from": 90, "to": 200}, "text": " mundo\n"},
                {"offsets": {"from": 150, "to": 180}, "text": " tragado"},
            ]
        },
    )

    result = _transcribe(_provider(cli, models, tmp_path), language="es")

    assert [(s.start_ms, s.end_ms, s.text) for s in result.segments] == [
        (0, 100, " hola"),
        (100, 200, " mundo"),
    ]
    assert result.language == "es"  # falls back to the requested hint


def test_tokens_become_words_with_probability(
    cli: Path, models: _Resolver, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def token(text: str, start: int, end: int, p: float) -> dict[str, object]:
        return {"text": text, "offsets": {"from": start, "to": end}, "p": p}

    _payload(
        tmp_path,
        monkeypatch,
        {
            "transcription": [
                {
                    "offsets": {"from": 0, "to": 400},
                    "text": " Hola mundo.",
                    "tokens": [
                        token("[_BEG_]", 0, 0, 1.0),
                        token(" Ho", 0, 120, 0.8),
                        token("la", 120, 200, 0.6),
                        token(" mundo", 200, 380, 0.9),
                        token(".", 380, 400, 0.5),
                        token("[_TT_20]", 400, 400, 0.1),
                    ],
                }
            ]
        },
    )

    [segment] = _transcribe(_provider(cli, models, tmp_path)).segments

    assert [(w.text, w.start_ms, w.end_ms) for w in segment.words] == [
        (" Hola", 0, 200),
        (" mundo.", 200, 400),
    ]
    assert segment.words[0].probability is not None
    assert abs(segment.words[0].probability - 0.7) < 1e-9
    assert (
        _transcribe(_provider(cli, models, tmp_path), word_timestamps=False)
        .segments[0]
        .words
        == ()
    )


def test_tokens_without_timestamps_leave_the_segment_without_words(
    cli: Path, models: _Resolver, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _payload(
        tmp_path,
        monkeypatch,
        {
            "transcription": [
                {
                    "offsets": {"from": 0, "to": 400},
                    "text": " Hola",
                    "tokens": [{"text": " Hola", "offsets": {"from": -1, "to": -1}}],
                }
            ]
        },
    )

    [segment] = _transcribe(_provider(cli, models, tmp_path)).segments

    assert segment.text == " Hola"
    assert segment.words == ()


# --- S9.07 failures and cancellation ----------------------------------------


def test_nonzero_exit_is_a_typed_failure_without_paths(
    cli: Path, models: _Resolver, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_WCPP_MODE", "fail")

    with pytest.raises(TranscriptionError) as raised:
        _transcribe(_provider(cli, models, tmp_path))

    assert raised.value.code is _CODE.PROVIDER_FAILED
    assert str(tmp_path) not in raised.value.user_message
    assert list((tmp_path / "work").iterdir()) == []


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "[]",
        '{"transcription": "x"}',
        '{"transcription": [{"text": "a"}]}',
        '{"transcription": [{"text": "a", "offsets": {"from": "0", "to": 5}}]}',
        '{"transcription": [{"text": "a", "offsets": {"from": true, "to": 5}}]}',
    ],
)
def test_invalid_json_is_a_typed_failure(
    cli: Path,
    models: _Resolver,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    body: str,
) -> None:
    path = tmp_path / "payload.json"
    path.write_text(body, encoding="utf-8")
    monkeypatch.setenv("FAKE_WCPP_PAYLOAD", str(path))

    with pytest.raises(TranscriptionError) as raised:
        _transcribe(_provider(cli, models, tmp_path))

    assert raised.value.code is _CODE.PROVIDER_FAILED
    assert str(tmp_path) not in raised.value.user_message


def test_missing_json_output_is_a_typed_failure(
    cli: Path, models: _Resolver, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_WCPP_MODE", "nojson")

    with pytest.raises(TranscriptionError) as raised:
        _transcribe(_provider(cli, models, tmp_path))

    assert raised.value.code is _CODE.PROVIDER_FAILED


def test_missing_binary_is_a_typed_failure(models: _Resolver, tmp_path: Path) -> None:
    provider = _provider(tmp_path / "absent" / "whisper-cli", models, tmp_path)

    with pytest.raises(TranscriptionError) as raised:
        _transcribe(provider)

    assert raised.value.code is _CODE.PROVIDER_FAILED
    assert "absent" not in raised.value.user_message


def test_missing_model_file_and_foreign_model_are_model_not_installed(
    cli: Path, tmp_path: Path
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    provider = _provider(cli, _Resolver(empty), tmp_path)

    with pytest.raises(TranscriptionError) as missing:
        _transcribe(provider)
    foreign = ModelDescriptor(
        provider_id="faster-whisper",
        model_id="base",
        display_name="Other",
        capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    )
    with pytest.raises(TranscriptionError) as wrong, _WAV.open("rb") as audio:
        provider.transcribe(audio=audio, options=TranscriptionOptions(model=foreign))

    assert missing.value.code is _CODE.MODEL_NOT_INSTALLED
    assert wrong.value.code is _CODE.MODEL_NOT_INSTALLED


def test_unsafe_model_id_never_builds_a_path(
    cli: Path, models: _Resolver, tmp_path: Path
) -> None:
    unsafe = ModelDescriptor(
        provider_id="whisper-cpp",
        model_id="../escape",
        display_name="Unsafe",
        capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    )
    with pytest.raises(TranscriptionError) as raised, _WAV.open("rb") as audio:
        _provider(cli, models, tmp_path).transcribe(
            audio=audio, options=TranscriptionOptions(model=unsafe)
        )

    assert raised.value.code is _CODE.MODEL_NOT_INSTALLED


def test_non_normalized_audio_is_invalid_audio_before_spawning(
    cli: Path, models: _Resolver, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("FAKE_WCPP_LOG", str(log))

    with pytest.raises(TranscriptionError) as raised:
        _provider(cli, models, tmp_path).transcribe(
            audio=BytesIO(b"not-a-wave"),
            options=TranscriptionOptions(model=_DESCRIPTOR),
        )

    assert raised.value.code is _CODE.INVALID_AUDIO
    assert not log.exists()
    assert list((tmp_path / "work").iterdir()) == []


def test_cancellation_terminates_the_process_and_cleans_up(
    cli: Path, models: _Resolver, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_file = tmp_path / "pid"
    monkeypatch.setenv("FAKE_WCPP_MODE", "sleep")
    monkeypatch.setenv("FAKE_WCPP_PID", str(pid_file))

    with pytest.raises(TranscriptionError) as raised, _WAV.open("rb") as audio:
        _provider(cli, models, tmp_path).transcribe(
            audio=audio,
            options=TranscriptionOptions(model=_DESCRIPTOR),
            cancellation=_Cancel(pid_file),
        )

    assert raised.value.code is _CODE.CANCELLED
    pid = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert list((tmp_path / "work").iterdir()) == []
