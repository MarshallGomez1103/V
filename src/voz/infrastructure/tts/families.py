"""sherpa-onnx TTS model families: manifest files -> ``OfflineTts`` kwargs.

Pure (no ``sherpa_onnx`` import), so every family quirk is testable without the
runtime; the worker turns the result into config objects. Supported families
are described in ``docs/adr/0010-voice-engines-and-tts.md``.

Manifest ``files`` keys per family (values are paths):

* ``vits`` (Piper): ``model``, ``tokens``; optional ``data_dir``, ``lexicon``,
  ``dict_dir``;
* ``kitten``: ``model``, ``voices``, ``tokens``, ``data_dir``;
* ``kokoro``: ``model``, ``voices``, ``tokens``, ``data_dir``, plus any
  ``lexicon*`` keys (joined with commas in key order); ``lang`` comes from the
  voice name prefix (``ef_dora`` -> ``es``), so one model serves every language;
* ``matcha``: ``acoustic_model``, ``vocoder``, ``tokens``; optional
  ``data_dir``, ``lexicon``, ``dict_dir``.

Directory roles (``data_dir``, ``dict_dir``) may name the directory or any file
inside it (``espeak-ng-data/phontab``), because the provider checks that every
manifest entry is a file. A missing ``data_dir`` defaults to ``espeak-ng-data``
next to ``tokens`` (every measured tarball ships it there).

Voice names live in the ONNX metadata (``speaker_names``, ``n_speakers``); a
tiny protobuf scan reads them without onnx/onnxruntime and without loading the
graph, so the server can list voices in-process.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Final

from voz.domain.entities.voice import Voice

ESPEAK_DIR: Final = "espeak-ng-data"
_DIR_ROLES: Final = frozenset({"data_dir", "dict_dir"})
_ALIASES: Final = {"piper": "vits"}


@dataclass(frozen=True, slots=True)
class _Family:
    config_class: str
    required: tuple[str, ...]
    optional: tuple[str, ...]
    needs_espeak: bool


_FAMILIES: Final = {
    "vits": _Family(
        "OfflineTtsVitsModelConfig",
        ("model", "tokens"),
        ("data_dir", "lexicon", "dict_dir"),
        needs_espeak=False,
    ),
    "kitten": _Family(
        "OfflineTtsKittenModelConfig",
        ("model", "voices", "tokens", "data_dir"),
        (),
        needs_espeak=True,
    ),
    "kokoro": _Family(
        "OfflineTtsKokoroModelConfig",
        ("model", "voices", "tokens", "data_dir"),
        (),
        needs_espeak=True,
    ),
    "matcha": _Family(
        "OfflineTtsMatchaModelConfig",
        ("acoustic_model", "vocoder", "tokens"),
        ("data_dir", "lexicon", "dict_dir"),
        needs_espeak=False,
    ),
}
FAMILIES: Final = frozenset(_FAMILIES)

# Kokoro v1.0 voice prefixes (first letter of ``af_heart``, ``ef_dora``…) to the
# espeak-ng language its ``lang`` option expects.
# ponytail: only "en"/"es" were measured (V4-01); the rest follow Kokoro's
# naming and espeak-ng voice names, unverified.
KOKORO_LANGS: Final = {
    "a": "en-us",
    "b": "en-gb",
    "e": "es",
    "f": "fr",
    "h": "hi",
    "i": "it",
    "j": "ja",
    "p": "pt-br",
    "z": "zh",
}


class ModelFilesError(ValueError):
    """The family is unknown or its files are missing (``model_not_installed``)."""


@dataclass(frozen=True, slots=True)
class ModelConfig:
    """What the worker passes to ``sherpa_onnx``.

    ``OfflineTtsModelConfig(**{field: <config_class>(**kwargs)}, ...)``.
    """

    field: str
    config_class: str
    kwargs: Mapping[str, str]


def canonical_family(family: str) -> str:
    name = _ALIASES.get(family.strip().lower(), family.strip().lower())
    if name not in _FAMILIES:
        raise ModelFilesError(f"unsupported TTS family: {family!r}")
    return name


def _resolve(role: str, path: Path) -> str:
    if role in _DIR_ROLES:
        directory = path if path.is_dir() else path.parent
        if not path.exists() or not directory.is_dir():
            raise ModelFilesError(f"missing model directory: {role}")
        return str(directory)
    if not path.is_file():
        raise ModelFilesError(f"missing model file: {role}")
    return str(path)


def model_config(
    family: str, files: Mapping[str, str | Path], *, lang: str = ""
) -> ModelConfig:
    """Validate ``files`` for ``family`` and build the per-family kwargs."""
    name = canonical_family(family)
    spec = _FAMILIES[name]
    paths = {role: Path(value) for role, value in files.items()}
    if "data_dir" not in paths and "tokens" in paths:
        default = paths["tokens"].parent / ESPEAK_DIR
        if spec.needs_espeak or default.is_dir():
            paths["data_dir"] = default
    missing = [role for role in spec.required if role not in paths]
    if missing:
        raise ModelFilesError(f"missing model file: {', '.join(missing)}")
    kwargs = {
        role: _resolve(role, paths[role])
        for role in (*spec.required, *spec.optional)
        if role in paths
    }
    if name == "kokoro":
        lexicons = [
            _resolve(role, paths[role])
            for role in sorted(paths)
            if role.startswith("lexicon")
        ]
        if lexicons:
            kwargs["lexicon"] = ",".join(lexicons)
        if lang:
            kwargs["lang"] = lang
    return ModelConfig(name, spec.config_class, kwargs)


def metadata_model_path(files: Mapping[str, str | Path]) -> Path:
    """The ONNX file whose metadata names the speakers."""
    value = files.get("model") or files.get("acoustic_model")
    if not value:
        raise ModelFilesError("missing model file: model")
    return Path(value)


# --- model directory discovery (catalog, import, opt-in tests) -----------------


def _one(directory: Path, pattern: str) -> Path:
    found = sorted(path for path in directory.glob(pattern) if path.is_file())
    if len(found) != 1:
        raise ModelFilesError(f"expected one {pattern} in the model directory")
    return found[0]


def discover_files(family: str, directory: Path) -> dict[str, Path]:
    """Manifest ``files`` for an extracted sherpa-onnx release tarball."""
    name = canonical_family(family)
    if name == "matcha":
        raise ModelFilesError("matcha models need explicit acoustic/vocoder files")
    files = {"model": _one(directory, "*.onnx"), "tokens": directory / "tokens.txt"}
    if name in {"kitten", "kokoro"}:
        files["voices"] = directory / "voices.bin"
    espeak = directory / ESPEAK_DIR / "phontab"
    if espeak.is_file():
        files["data_dir"] = espeak
    if name == "kokoro":  # V4-01: exactly these two, in this order
        for key, filename in (
            ("lexicon_1", "lexicon-us-en.txt"),
            ("lexicon_2", "lexicon-zh.txt"),
        ):
            if (directory / filename).is_file():
                files[key] = directory / filename
    model_config(name, files)  # validate
    return files


# --- voices from ONNX metadata ------------------------------------------------

_METADATA_FIELD: Final = 14  # ModelProto.metadata_props
_MAX_ENTRY_BYTES: Final = 1 << 20


def _varint(stream: IO[bytes]) -> int | None:
    result = shift = 0
    while True:
        byte = stream.read(1)
        if not byte:
            if shift:
                raise ModelFilesError("truncated ONNX file")
            return None
        result |= (byte[0] & 0x7F) << shift
        if not byte[0] & 0x80:
            return result
        shift += 7
        if shift > 63:
            raise ModelFilesError("malformed ONNX file")


def _entry(raw: bytes) -> tuple[str, str]:
    """Decode a ``StringStringEntryProto`` (key = 1, value = 2)."""
    fields = {1: "", 2: ""}
    pos = 0
    while pos < len(raw):
        tag, pos = _varint_bytes(raw, pos)
        if tag & 7 != 2:
            raise ModelFilesError("malformed ONNX metadata")
        size, pos = _varint_bytes(raw, pos)
        fields[tag >> 3] = raw[pos : pos + size].decode("utf-8", "replace")
        pos += size
    return fields[1], fields[2]


def _varint_bytes(raw: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while pos < len(raw):
        byte = raw[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
    raise ModelFilesError("malformed ONNX metadata")


def read_onnx_metadata(path: Path) -> dict[str, str]:
    """``metadata_props`` of an ONNX model, skipping the graph by seeking."""
    metadata: dict[str, str] = {}
    size_on_disk = path.stat().st_size
    with path.open("rb") as stream:
        while (tag := _varint(stream)) is not None:
            wire = tag & 7
            if wire == 0:
                _varint(stream)
            elif wire == 1:
                stream.seek(8, 1)
            elif wire == 5:
                stream.seek(4, 1)
            elif wire == 2:
                size = _varint(stream)
                if size is None:
                    raise ModelFilesError("truncated ONNX file")
                if tag >> 3 == _METADATA_FIELD and size <= _MAX_ENTRY_BYTES:
                    raw = stream.read(size)
                    if len(raw) != size:
                        raise ModelFilesError("truncated ONNX file")
                    key, value = _entry(raw)
                    metadata[key] = value
                else:
                    stream.seek(size, 1)
            else:
                raise ModelFilesError("malformed ONNX file")
            if stream.tell() > size_on_disk:
                raise ModelFilesError("truncated ONNX file")
    return metadata


def speaker_names(metadata: Mapping[str, str]) -> tuple[str, ...]:
    """Speaker names by sid; empty when the model does not name them."""
    names = metadata.get("speaker_names", "")
    if names.strip():
        return tuple(name.strip() for name in names.split(","))
    try:
        mapping = json.loads(metadata.get("id2speaker", ""))
    except ValueError:
        return ()
    if not isinstance(mapping, dict):
        return ()
    by_id = {str(k): str(v) for k, v in mapping.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    if set(by_id) != {str(i) for i in range(len(by_id))}:
        return ()
    return tuple(by_id[str(i)] for i in range(len(by_id)))


def speaker_count(metadata: Mapping[str, str]) -> int:
    try:
        count = int(metadata.get("n_speakers", "1"))
    except ValueError:
        count = 1
    return max(count, len(speaker_names(metadata)), 1)


def kokoro_lang(voice_name: str) -> str:
    """espeak-ng language for a Kokoro voice name, ``""`` when unknown."""
    return KOKORO_LANGS.get(voice_name[:1].lower(), "") if "_" in voice_name else ""


def resolve_sid(voice_id: str, names: tuple[str, ...], count: int) -> int | None:
    """Speaker id for ``voice_id`` (a sid as text, or a speaker name)."""
    if voice_id.isascii() and voice_id.isdigit():
        sid = int(voice_id)
        return sid if sid < count else None
    return names.index(voice_id) if voice_id in names else None


_GENERIC_NAME: Final = re.compile(r"(speaker[\s_-]*)?\d+", re.IGNORECASE)


def _named(names: tuple[str, ...], sid: int) -> str:
    """The ONNX name of ``sid``; ``""`` when absent or only a synthesized id."""
    name = names[sid] if sid < len(names) else ""
    return "" if _GENERIC_NAME.fullmatch(name) else name


def read_voices(
    family: str,
    files: Mapping[str, str | Path],
    languages: tuple[str, ...] = (),
    curated: tuple[Voice, ...] = (),
) -> tuple[Voice, ...]:
    """Voices of an installed model (``id`` = sid as text) from its metadata.

    Real ONNX names win. Where the model names no speaker (or only ``Speaker 0``
    style ids; Piper's single-voice ONNX does not) the ``curated`` voice with the
    same id supplies the name, then ``Speaker <sid>``.
    """
    name = canonical_family(family)
    try:
        metadata = read_onnx_metadata(metadata_model_path(files))
    except OSError as error:
        raise ModelFilesError("cannot read the model file") from error
    names = speaker_names(metadata)
    backup = {voice.id: voice for voice in curated}
    voices: list[Voice] = []
    for sid in range(speaker_count(metadata)):
        fallback = backup.get(str(sid))
        label = _named(names, sid)
        voice_languages = languages
        if not label and fallback:
            label, voice_languages = fallback.name, fallback.languages
        label = label or f"Speaker {sid}"
        lang = kokoro_lang(label) if name == "kokoro" else ""
        voices.append(
            Voice(str(sid), label, (lang.split("-")[0],) if lang else voice_languages)
        )
    return tuple(voices)


__all__ = [
    "ESPEAK_DIR",
    "FAMILIES",
    "KOKORO_LANGS",
    "ModelConfig",
    "ModelFilesError",
    "canonical_family",
    "discover_files",
    "kokoro_lang",
    "metadata_model_path",
    "model_config",
    "read_onnx_metadata",
    "read_voices",
    "resolve_sid",
    "speaker_count",
    "speaker_names",
]
