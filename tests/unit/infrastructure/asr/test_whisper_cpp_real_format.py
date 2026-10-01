"""The adapter reads a real ``whisper-cli -ojf`` file (S9.10 format validation).

``real_ojf_v1.9.4.json`` was produced by whisper.cpp v1.9.4 with the adapter's own
flags on a synthetic Spanish clip (first two segments, paths redacted).
"""

import os
import stat
import sys
from io import BytesIO
from pathlib import Path

import pytest

from voz.application.ports.transcription import TranscriptionOptions
from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.infrastructure.asr.whisper_cpp import WhisperCppProvider

_FIXTURES = Path(__file__).parents[3] / "fixtures"
_DESCRIPTOR = ModelDescriptor(
    provider_id="whisper-cpp",
    model_id="base",
    display_name="whisper.cpp base",
    capabilities=frozenset({ModelCapability.TRANSCRIPTION}),
    source="example/whisper-cpp-fixture",
    revision="e" * 40,
)


class _Resolver:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def resolve_path(self, descriptor: ModelDescriptor) -> Path:
        del descriptor
        return self.directory


def test_real_whisper_cli_json_maps_to_segments_and_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "whisper-cli"
    fake = (_FIXTURES / "whisper_cpp/fake_whisper_cli.py").read_text()
    binary.write_text(f"#!{sys.executable}\n{fake}", encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv(
        "FAKE_WCPP_PAYLOAD", str(_FIXTURES / "whisper_cpp/real_ojf_v1.9.4.json")
    )
    models = tmp_path / "model"
    models.mkdir()
    (models / "ggml-base.bin").write_bytes(b"ggml")
    work = tmp_path / "work"
    work.mkdir()
    provider = WhisperCppProvider(
        binary=binary, model_resolver=_Resolver(models), temp_root=work
    )
    wav = (_FIXTURES / "media/synthetic-tone.wav").read_bytes()

    result = provider.transcribe(
        audio=BytesIO(wav),
        options=TranscriptionOptions(
            model=_DESCRIPTOR, language="es", word_timestamps=True
        ),
    )

    assert result.language == "es"
    first, second = result.segments
    assert (first.start_ms, first.end_ms) == (0, 4440)
    assert first.text.strip().startswith("Para preparar un buen café")
    assert second.start_ms >= first.end_ms
    assert [word.text.strip() for word in first.words][:3] == ["Para", "preparar", "un"]
    assert os.listdir(work) == []
