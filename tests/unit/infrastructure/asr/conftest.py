"""Keep ASR infrastructure tests hermetic: never spawn nvidia-smi or read the host."""

import os
from collections.abc import Mapping

import pytest

from voz.infrastructure import child_env
from voz.infrastructure.asr import hardware, sherpa_onnx, whisper_cpp


@pytest.fixture(autouse=True)
def no_host_measurement(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hardware, "read_gpu_memory", lambda: None)
    monkeypatch.setattr(hardware, "read_system_memory", lambda: None)


@pytest.fixture(autouse=True)
def fake_worker_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake workers are steered by FAKE_* variables the real filter would drop."""

    def with_fake_controls(extra: Mapping[str, str] | None = None) -> dict[str, str]:
        controls = {k: v for k, v in os.environ.items() if k.startswith("FAKE_")}
        return child_env.child_environment({**controls, **(extra or {})})

    monkeypatch.setattr(sherpa_onnx, "child_environment", with_fake_controls)
    monkeypatch.setattr(whisper_cpp, "child_environment", with_fake_controls)
