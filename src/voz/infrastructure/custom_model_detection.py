"""Conservative format hints from filenames, never downloaded model code."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from voz.application.ports.custom_models import CustomModelError


def _selection(
    candidates: list[tuple[str, str, dict[str, str]]], *, ambiguous: bool = False
) -> tuple[str, str, dict[str, str]]:
    if ambiguous or len(candidates) > 1:
        raise CustomModelError(
            "custom_model_detection_ambiguous",
            "Several model formats or file sets were found. Select the engine "
            "and family manually.",
        )
    if not candidates:
        raise CustomModelError(
            "custom_model_engine_unsupported",
            "The model format could not be identified safely. Select a supported "
            "engine and family manually, or choose compatible model files.",
        )
    return candidates[0]


def _tts_families(label: str) -> set[str]:
    return {
        "vits" if tag == "piper" else tag
        for tag in ("kitten", "kokoro", "vits", "piper")
        if re.search(r"(?:^|[^a-z0-9])" + tag + r"(?:$|[^a-z0-9])", label.lower())
    }


def detect_download(name: str) -> tuple[str, str, dict[str, str]]:
    """Archive names are hints only; installation must still load-validate them."""
    candidates: list[tuple[str, str, dict[str, str]]] = []
    if name.startswith("ggml-") and name.endswith(".bin"):
        candidates.append(("whisper-cpp", "ggml", {}))
    if name.endswith(".tar.bz2"):
        if re.search(r"(?:^|[-_.])whisper(?:$|[-_.])", name.lower()):
            candidates.append(("sherpa-onnx-asr", "whisper", {}))
        candidates.extend(
            ("sherpa-onnx-tts", family, {}) for family in _tts_families(name)
        )
    return _selection(candidates)


def detect_repository(
    names: set[str], repository: str
) -> tuple[str, str, dict[str, str]]:
    """Recognize complete supported layouts; ambiguous weights require review."""
    candidates: list[tuple[str, str, dict[str, str]]] = []
    ambiguous = False
    if {"model.bin", "config.json", "tokenizer.json"} <= names:
        candidates.append(("faster-whisper", "ctranslate2", {}))
    ggml = [
        name
        for name in names
        if "/" not in name and name.startswith("ggml-") and name.endswith(".bin")
    ]
    if len(ggml) == 1:
        candidates.append(("whisper-cpp", "ggml", {}))
    ambiguous |= len(ggml) > 1
    onnx = {name for name in names if name.endswith(".onnx")}
    roles = {
        role: [
            name
            for name in onnx
            if re.fullmatch(
                r"(?:.*[-_])?" + role + r"(?:\.int8)?\.onnx", PurePosixPath(name).name
            )
        ]
        for role in ("encoder", "decoder")
    }
    tokens = [name for name in names if PurePosixPath(name).name == "tokens.txt"]
    if roles["encoder"] and roles["decoder"] and tokens:
        if (
            len(onnx) == 2
            and all(len(found) == 1 for found in roles.values())
            and len(tokens) == 1
        ):
            candidates.append(
                (
                    "sherpa-onnx-asr",
                    "whisper",
                    {
                        "encoder": roles["encoder"][0],
                        "decoder": roles["decoder"][0],
                        "tokens": tokens[0],
                    },
                )
            )
        else:
            ambiguous = True
    label = repository.rsplit("/", 1)[-1] + " " + " ".join(sorted(onnx))
    families = _tts_families(label)
    if families and "tokens.txt" in names and onnx:
        if len(onnx) != 1 or any("/" in name for name in onnx) or len(families) > 1:
            ambiguous = True
        else:
            family = next(iter(families))
            if family == "vits" or {"voices.bin", "espeak-ng-data/phontab"} <= names:
                candidates.append(("sherpa-onnx-tts", family, {}))
    # ponytail: infer only complete filename layouts; the isolated loader proves
    # compatibility after confirmation. Unknown layouts remain a manual choice.
    return _selection(candidates, ambiguous=ambiguous)
