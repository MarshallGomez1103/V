"""Keep ASR infrastructure tests hermetic: never spawn nvidia-smi or read the host."""

import pytest

from voz.infrastructure.asr import hardware


@pytest.fixture(autouse=True)
def no_host_measurement(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hardware, "read_gpu_memory", lambda: None)
    monkeypatch.setattr(hardware, "read_system_memory", lambda: None)
