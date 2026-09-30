"""whisper.cpp options: installation by single file, binary probe cached."""

from pathlib import Path

from voz.application.ports.transcription_options import InstallationStatus
from voz.infrastructure.asr.whisper_cpp import (
    WhisperCppAvailability,
    WhisperCppUnavailableReason,
)
from voz.infrastructure.asr.whisper_cpp_options import (
    WhisperCppRuntimeProbe,
    WhisperCppTranscriptionModelCatalog,
)
from voz.infrastructure.model_storage import FileSystemModelStore


def test_uninstalled_models_are_listed_but_not_registered(tmp_path: Path) -> None:
    store = FileSystemModelStore(data_root=tmp_path / "d", cache_root=tmp_path / "c")
    registrations = WhisperCppTranscriptionModelCatalog(store).list_models()
    assert registrations
    assert all(
        r.installation_status is InstallationStatus.NOT_REGISTERED
        and r.descriptor.profile is not None
        for r in registrations
    )


def test_probe_is_cached_and_reports_cpu_only() -> None:
    calls: list[int] = []

    def fake() -> WhisperCppAvailability:
        calls.append(1)
        return WhisperCppAvailability(True, binary=Path("/x/whisper-cli"))

    probe = WhisperCppRuntimeProbe(fake)
    first = probe.probe("whisper-cpp")
    probe.probe("whisper-cpp")
    assert calls == [1]
    assert first.available
    assert first.hardware is not None
    assert first.hardware.cuda_compute_types == frozenset()


def test_missing_binary_is_unavailable() -> None:
    probe = WhisperCppRuntimeProbe(
        lambda: WhisperCppAvailability(False, WhisperCppUnavailableReason.NOT_FOUND)
    )
    assert not probe.probe("whisper-cpp").available
