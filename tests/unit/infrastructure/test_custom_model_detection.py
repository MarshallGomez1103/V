"""Conservative format detection does not require runtime imports or weights."""

from __future__ import annotations

import pytest

from voz.application.ports.custom_models import CustomModelError
from voz.infrastructure.custom_model_detection import detect_download, detect_repository


@pytest.mark.parametrize(
    ("repo", "names", "code"),
    [
        (
            "generic",
            {"model.onnx", "tokens.txt", "voices.bin", "espeak-ng-data/phontab"},
            "custom_model_engine_unsupported",
        ),
        (
            "kitten",
            {"model.onnx", "tokens.txt", "voices.bin"},
            "custom_model_engine_unsupported",
        ),
        (
            "kokoro",
            {"model.onnx", "tokens.txt", "espeak-ng-data/phontab"},
            "custom_model_engine_unsupported",
        ),
        (
            "kokoro-kitten",
            {"model.onnx", "tokens.txt", "voices.bin", "espeak-ng-data/phontab"},
            "custom_model_detection_ambiguous",
        ),
        (
            "piper",
            {"model.onnx", "extra.onnx", "tokens.txt"},
            "custom_model_detection_ambiguous",
        ),
        (
            "whisper",
            {"encoder.onnx", "decoder.onnx", "tokens.txt", "nested/tokens.txt"},
            "custom_model_detection_ambiguous",
        ),
        ("whisper", {"encoder.onnx", "tokens.txt"}, "custom_model_engine_unsupported"),
        ("ct2", {"model.bin", "config.json"}, "custom_model_engine_unsupported"),
    ],
)
def test_incomplete_or_ambiguous_layouts_require_manual_review(
    repo: str,
    names: set[str],
    code: str,
) -> None:
    with pytest.raises(CustomModelError) as raised:
        detect_repository(names, "org/" + repo)
    assert raised.value.code == code


def test_tagged_archive_with_multiple_families_is_ambiguous() -> None:
    with pytest.raises(CustomModelError) as raised:
        detect_download("kokoro-whisper.tar.bz2")
    assert raised.value.code == "custom_model_detection_ambiguous"
