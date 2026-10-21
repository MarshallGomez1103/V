"""NeMo dispatch uses trusted installed loaders and explicit CPU-only files."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from voz.application.ports.custom_models import CustomModelError, CustomValidation
from voz.application.ports.transcription import TranscriptionError
from voz.infrastructure import custom_model_worker, custom_models
from voz.infrastructure.asr import sherpa_onnx_worker as worker
from voz.infrastructure.asr.sherpa_onnx_options import nemo_transducer_files
from voz.infrastructure.custom_model_detection import detect_download, detect_repository


def model(root: Path) -> dict[str, Path]:
    for name in (
        "encoder.int8.onnx",
        "decoder.int8.onnx",
        "joiner.int8.onnx",
        "tokens.txt",
    ):
        (root / name).write_bytes(b"weights")
    return nemo_transducer_files(root)


def test_native_nemo_factory_is_explicit_cpu_two_threads(tmp_path: Path) -> None:
    files = model(tmp_path)
    factory = Mock()
    worker.load_nemo_transducer(files, factory=factory)
    factory.assert_called_once_with(
        **{r: str(p) for r, p in files.items()},
        provider="cpu",
        num_threads=2,
        debug=False,
        decoding_method="greedy_search",
        model_type="nemo_transducer",
    )


def test_validator_dispatches_nemo_and_rejects_unknown_without_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = model(tmp_path)
    load = Mock()
    monkeypatch.setattr(custom_model_worker, "load_nemo_transducer", load)
    assert (
        custom_model_worker._load(tmp_path, "sherpa-onnx-asr", "nemo_transducer", {})  # pyright: ignore[reportPrivateUsage]
        == CustomValidation()
    )
    load.assert_called_once_with(files)
    with pytest.raises(ValueError):
        custom_model_worker._load(tmp_path, "sherpa-onnx-asr", "unknown", {})  # pyright: ignore[reportPrivateUsage]
    assert load.call_count == 1


@pytest.mark.parametrize(
    "bad",
    [
        "../outside.onnx",
        "/outside.onnx",
        "nested/../../outside.onnx",
        "C:/outside.onnx",
        "joiner.py",
    ],
)
def test_nemo_role_boundary_rejects_unsafe_before_loader(
    tmp_path: Path, bad: str
) -> None:
    files = model(tmp_path)
    roles = {r: p.name for r, p in files.items()}
    roles["joiner"] = bad
    with pytest.raises(TranscriptionError):
        nemo_transducer_files(tmp_path, roles)
    with pytest.raises(CustomModelError):
        custom_models.model_files(tmp_path, "nemo_transducer", roles)


def test_nemo_discovery_requires_unique_four_regular_files(tmp_path: Path) -> None:
    files = model(tmp_path)
    roles = {r: p.name for r, p in files.items()}
    (tmp_path / "joiner.int8.onnx").unlink()
    with pytest.raises(TranscriptionError):
        nemo_transducer_files(tmp_path)
    (tmp_path / "joiner.int8.onnx").symlink_to(files["encoder"])
    with pytest.raises(TranscriptionError):
        nemo_transducer_files(tmp_path, roles)
    with pytest.raises(TranscriptionError):
        nemo_transducer_files(
            tmp_path, {r: n for r, n in roles.items() if r != "joiner"}
        )


def test_nemo_detection_never_confuses_three_weights_with_whisper() -> None:
    names = {"encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"}
    engine, family, roles = detect_repository(names, "vendor/nemo-parakeet-tdt")
    assert (engine, family) == ("sherpa-onnx-asr", "nemo_transducer")
    assert set(roles) == {"encoder", "decoder", "joiner", "tokens"}
    assert detect_download("sherpa-onnx-nemo-parakeet-tdt-v3-int8.tar.bz2") == (
        "sherpa-onnx-asr",
        "nemo_transducer",
        {},
    )
    for incomplete in (names - {"tokens.txt"}, names - {"joiner.int8.onnx"}):
        with pytest.raises(CustomModelError):
            detect_repository(incomplete, "vendor/nemo-parakeet-tdt")
    with pytest.raises(CustomModelError):
        detect_repository(names, "vendor/unknown-transducer")


def test_worker_dispatch_does_not_load_other_families_or_apply_language_hints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = model(tmp_path)
    nemo = Mock()
    whisper = Mock()
    monkeypatch.setattr(worker, "load_nemo_transducer", nemo)
    monkeypatch.setattr(worker, "load_whisper", whisper)
    assert worker.load_recognizer("nemo_transducer", files, None) is nemo.return_value
    assert worker.load_recognizer("whisper", files, "es") is whisper.return_value
    for family, language in [("unknown", None), ("nemo_transducer", "es")]:
        with pytest.raises(ValueError):
            worker.load_recognizer(family, files, language)
    nemo.assert_called_once_with(files)
    whisper.assert_called_once_with(files, "es")


@pytest.mark.parametrize("fails", [False, True])
def test_nemo_isolated_validator_loads_only_the_installed_factory(
    tmp_path: Path, fails: bool
) -> None:
    import os
    import sys

    from voz.infrastructure.custom_model_worker import SubprocessModelValidator

    pytest.importorskip("sherpa_onnx")
    model(tmp_path)
    child = """
import os,sys
from pathlib import Path
import sherpa_onnx
from voz.infrastructure.custom_model_worker import main
folder=Path(sys.argv[3])
def factory(**kwargs):
    assert kwargs['provider']=='cpu' and kwargs['num_threads']==2
    assert kwargs['model_type']=='nemo_transducer'
    assert kwargs['decoding_method']=='greedy_search'
    assert 'language' not in kwargs and 'task' not in kwargs
    for role in ('encoder','decoder','joiner','tokens'):
        assert Path(kwargs[role]).is_file()
    (folder/'.factory-pid').write_text(str(os.getpid()))
    return object()
sherpa_onnx.OfflineRecognizer.from_transducer=staticmethod(factory)
sys.exit(main())
"""
    if fails:
        child = child.replace("return object()", "raise RuntimeError('private-secret')")
    validator = SubprocessModelValidator(
        argv=[sys.executable, "-c", child], timeout_seconds=10
    )
    if fails:
        with pytest.raises(CustomModelError) as failure:
            validator.validate(
                tmp_path,
                "sherpa-onnx-asr",
                "nemo_transducer",
                file_roles={},
                cancelled=lambda: False,
            )
        assert failure.value.code == "custom_model_validation_failed"
        assert "private-secret" not in str(failure.value)
    else:
        assert (
            validator.validate(
                tmp_path,
                "sherpa-onnx-asr",
                "nemo_transducer",
                file_roles={},
                cancelled=lambda: False,
            )
            == CustomValidation()
        )
    assert int((tmp_path / ".factory-pid").read_text()) != os.getpid()


def test_nemo_explicit_roles_reject_symlinked_parent_and_duplicate_files(
    tmp_path: Path,
) -> None:
    files = model(tmp_path)
    roles = {role: path.name for role, path in files.items()}
    with pytest.raises(TranscriptionError):
        nemo_transducer_files(tmp_path, {**roles, "joiner": roles["encoder"]})
    outside = tmp_path / "real"
    outside.mkdir()
    (outside / "joiner.onnx").write_bytes(b"weights")
    (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(TranscriptionError):
        nemo_transducer_files(tmp_path, {**roles, "joiner": "link/joiner.onnx"})


@pytest.mark.parametrize("label", ["sherpa-onnx-nemo-ctc.tar.bz2", "nemo.tar.bz2"])
def test_nemo_ctc_archive_name_is_not_guessed_as_transducer(label: str) -> None:
    with pytest.raises(CustomModelError) as failure:
        detect_download(label)
    assert failure.value.code == "custom_model_engine_unsupported"
