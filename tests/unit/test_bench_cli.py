"""Tests for ``voz bench``: dataset loading, privacy guard and measurements."""

from __future__ import annotations

import json
import wave
from pathlib import Path
from typing import BinaryIO

import pytest
from typer.testing import CliRunner

from voz.application.ports.transcription import (
    TranscriptionCancellationToken,
    TranscriptionOptions,
    TranscriptionResult,
    TranscriptionSegment,
)
from voz.domain.entities.model_descriptor import ModelDescriptor
from voz.infrastructure.asr.catalog import faster_whisper_catalog
from voz.interfaces.cli import bench
from voz.interfaces.cli.bench import (
    BenchmarkError,
    VramSampler,
    checkout_root,
    ensure_outside_checkout,
    find_descriptor,
    load_dataset,
    render_text,
    resolve_dataset_dir,
    run_benchmark,
)
from voz.interfaces.cli.main import app as cli_app


def _wav(path: Path, seconds: int) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(bytes(2 * 16_000 * seconds))


def _dataset(root: Path, items: list[dict[str, str]], **extra: object) -> Path:
    root.mkdir(parents=True)
    (root / "manifest.json").write_text(
        json.dumps({"language": "es", "items": items, **extra})
    )
    return root


class _FakeProvider:
    """Answers the warm-up with nothing and each clip with a fixed sentence."""

    provider_id = "faster-whisper"

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls = 0

    def transcribe(
        self,
        *,
        audio: BinaryIO,
        options: TranscriptionOptions,
        cancellation: TranscriptionCancellationToken | None = None,
    ) -> TranscriptionResult:
        self.calls += 1
        del audio, options, cancellation
        return TranscriptionResult(
            segments=(TranscriptionSegment(0, 1000, self._text),), language="es"
        )


def _descriptor() -> ModelDescriptor:
    return find_descriptor(
        "faster-whisper",
        "Systran/faster-whisper-large-v3",
        "edaa852ec7e145841d8ffdb056a99866b5f0a478",
    )


def test_load_dataset_reads_inline_and_file_references(tmp_path: Path) -> None:
    root = _dataset(
        tmp_path / "mio",
        [
            {"audio": "a.wav", "reference": "hola mundo"},
            {"audio": "b.wav", "reference_file": "b.txt"},
            {"audio": "c.wav"},
        ],
    )
    for name in ("a.wav", "b.wav", "c.wav"):
        _wav(root / name, 1)
    (root / "b.txt").write_text("segunda frase", "utf-8")
    dataset = load_dataset(root)
    assert dataset.name == "mio"
    assert dataset.language == "es"
    assert [item.reference for item in dataset.items] == [
        "hola mundo",
        "segunda frase",
        None,
    ]


@pytest.mark.parametrize(
    "items",
    [
        [],
        [{"audio": "../fuera.wav"}],
        [{"audio": "no_existe.wav"}],
        [{"audio": ""}],
    ],
)
def test_load_dataset_rejects_invalid_manifests(
    tmp_path: Path, items: list[dict[str, str]]
) -> None:
    (tmp_path / "fuera.wav").write_bytes(b"x")
    root = _dataset(tmp_path / "ds", items)
    with pytest.raises(BenchmarkError) as error:
        load_dataset(root)
    assert error.value.code == "benchmark_manifest_invalid"


def test_load_dataset_without_manifest_fails(tmp_path: Path) -> None:
    with pytest.raises(BenchmarkError) as error:
        load_dataset(tmp_path)
    assert error.value.code == "benchmark_manifest_invalid"


def test_dataset_inside_the_checkout_is_refused() -> None:
    root = checkout_root()
    assert root is not None  # tests run from the source checkout
    with pytest.raises(BenchmarkError) as error:
        ensure_outside_checkout(root / "benchmarks" / "x", repo_root=root)
    assert error.value.code == "benchmark_dataset_inside_checkout"


def test_resolve_dataset_dir_refuses_data_home_inside_checkout() -> None:
    root = checkout_root()
    assert root is not None
    with pytest.raises(BenchmarkError) as error:
        resolve_dataset_dir(
            "x", benchmarks_dir=root / ".local" / "voz" / "benchmarks", repo_root=root
        )
    assert error.value.code == "benchmark_dataset_inside_checkout"


def test_resolve_dataset_dir_accepts_name_and_path(tmp_path: Path) -> None:
    (tmp_path / "bench" / "uno").mkdir(parents=True)
    by_name = resolve_dataset_dir(
        "uno", benchmarks_dir=tmp_path / "bench", repo_root=None
    )
    by_path = resolve_dataset_dir(
        str(tmp_path / "bench" / "uno"), benchmarks_dir=tmp_path, repo_root=None
    )
    assert by_name == by_path == tmp_path / "bench" / "uno"
    with pytest.raises(BenchmarkError) as error:
        resolve_dataset_dir("otro", benchmarks_dir=tmp_path / "bench", repo_root=None)
    assert error.value.code == "benchmark_dataset_not_found"


def test_find_descriptor_requires_a_pinned_catalog_match() -> None:
    assert _descriptor().model_id == "large-v3"
    with pytest.raises(BenchmarkError) as error:
        find_descriptor("faster-whisper", "Systran/faster-whisper-large-v3", "0" * 40)
    assert error.value.code == "benchmark_model_unknown"
    assert faster_whisper_catalog()  # catalog unchanged by the lookup


def test_run_benchmark_scores_time_rtf_and_error_rates(tmp_path: Path) -> None:
    root = _dataset(
        tmp_path / "ds",
        [
            {"audio": "a.wav", "reference": "hola mundo"},
            {"audio": "b.wav"},
        ],
    )
    _wav(root / "a.wav", 2)
    _wav(root / "b.wav", 2)
    ticks = iter([0.0, 3.0, 3.0, 4.0, 4.0, 5.0])
    provider = _FakeProvider("Hola, mundo.")
    report = run_benchmark(
        provider=provider,
        descriptor=_descriptor(),
        dataset=load_dataset(root),
        language="es",
        device="cpu",
        compute_type="int8",
        clock=lambda: next(ticks),
        vram_read=lambda: None,
    )
    assert provider.calls == 3  # warm-up plus two clips
    assert abs(report.load_seconds - 3.0) < 1e-9
    first, second = report.items
    assert abs(first.rtf - 0.5) < 1e-9
    assert (first.wer, first.cer) == (0.0, 0.0)
    assert (second.wer, second.cer) == (None, None)
    assert abs(report.totals.rtf - 0.5) < 1e-9
    assert report.totals.wer == 0.0
    assert report.memory.vram_peak_mib is None
    assert report.memory.ram_peak_mib > 0
    assert "TOTAL" in render_text(report)


def test_vram_sampler_tracks_peak_and_baseline() -> None:
    values = iter([100, 900, 400, 400, 400, 400, 400, 400, 400, 400])
    with VramSampler(lambda: next(values, 400), interval=0.001) as sampler:
        pass
    assert sampler.baseline == 100
    assert sampler.peak is not None and sampler.peak >= 400


def test_vram_sampler_without_gpu_reports_none() -> None:
    with VramSampler(lambda: None) as sampler:
        pass
    assert sampler.baseline is None
    assert sampler.peak is None


def test_cli_refuses_a_data_home_inside_the_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = checkout_root()
    assert root is not None
    monkeypatch.setenv("XDG_DATA_HOME", str(root / ".pytest-bench-data"))
    result = CliRunner().invoke(
        cli_app,
        [
            "bench",
            "--model-dir",
            str(tmp_path),
            "--source",
            "Systran/faster-whisper-large-v3",
            "--revision",
            "edaa852ec7e145841d8ffdb056a99866b5f0a478",
            "--dataset",
            "x",
        ],
    )
    assert result.exit_code == 2
    assert "benchmark_dataset_inside_checkout" in result.output
    assert not (root / ".pytest-bench-data").exists()


def test_cli_rejects_unsupported_options(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli_app,
        [
            "bench",
            "--model-dir",
            str(tmp_path),
            "--source",
            "s",
            "--revision",
            "r",
            "--dataset",
            "x",
            "--engine",
            "whisper-cpp",
            "--device",
            "cuda",
        ],
    )
    assert result.exit_code == 2
    assert "benchmark_option_invalid" in result.output


def test_cli_json_output_end_to_end_with_fake_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data_home = tmp_path / "data"
    root = _dataset(
        data_home / "voz" / "benchmarks" / "mio",
        [{"audio": "a.wav", "reference": "hola mundo"}],
    )
    _wav(root / "a.wav", 1)
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))

    def fake_provider(
        engine: str, model_dir: Path, *, device: str, compute_type: str
    ) -> _FakeProvider:
        del engine, model_dir, device, compute_type
        return _FakeProvider("hola")

    monkeypatch.setattr(bench, "build_provider", fake_provider)
    monkeypatch.setattr(bench, "read_vram_used_mib", lambda: None)
    result = CliRunner().invoke(
        cli_app,
        [
            "bench",
            "--model-dir",
            str(tmp_path),
            "--source",
            "Systran/faster-whisper-large-v3",
            "--revision",
            "edaa852ec7e145841d8ffdb056a99866b5f0a478",
            "--dataset",
            "mio",
            "--device",
            "cpu",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dataset"] == "mio"
    assert payload["compute_type"] == "int8"
    assert abs(payload["totals"]["wer"] - 0.5) < 1e-9
    assert str(tmp_path) not in result.output


def test_find_descriptor_for_whisper_cpp_uses_the_model_id() -> None:
    from voz.infrastructure.asr.whisper_cpp_catalog import REVISION

    descriptor = find_descriptor("whisper-cpp", "large-v3-turbo-q5_0", REVISION)
    assert descriptor.model_id == "large-v3-turbo-q5_0"
    with pytest.raises(BenchmarkError):
        find_descriptor("whisper-cpp", "ggerganov/whisper.cpp", REVISION)
