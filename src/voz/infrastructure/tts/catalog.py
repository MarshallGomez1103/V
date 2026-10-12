"""Pinned catalog of the speech synthesis models V installs (ADR-0010, V4-01).

Every entry is a ``.tar.bz2`` from the ``tts-models`` release of
``k2-fsa/sherpa-onnx``, pinned by size and SHA-256 (the release is mutable) and
measured in ``.ai/v-plan/findings/V4-01.md``. Only the files listed here (plus the
``espeak-ng-data`` tree and the license notices) are ever extracted from an
archive. Models are addressed as ``"sherpa-onnx-tts:<model_id>"``.

Voice ids are the sherpa-onnx speaker ids (``sid``) as text. ``voices`` here is a
curated fallback: an installed model's manifest reads the real speaker names from
the ONNX metadata (``families.read_voices``) and uses this list only if that fails.
"""

from __future__ import annotations

from dataclasses import dataclass

from voz.domain.entities.model_descriptor import ModelCapability, ModelDescriptor
from voz.domain.entities.voice import Voice

TTS_PROVIDER_ID = "sherpa-onnx-tts"
TTS_REQUIRES = "tts"  # the sherpa-onnx runtime, as a Model Manager "requires" tag

_RELEASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"
_MIB = 1024 * 1024
_ESPEAK_DIR = "espeak-ng-data"
# The engine checks that every manifest path is a file, so ``data_dir`` is
# published as this file inside the directory (``families.discover_files``).
DATA_DIR_MARKER = "phontab"
# Informational files copied next to the model when the archive has them.
NOTICE_FILES = ("LICENSE", "MODEL_CARD")

_ESPEAK_NOTE = "espeak-ng-data GPL-3.0 (phoneme data included in the archive)"
_LESSAC_NOTE = "voice trained on lessac (Blizzard 2013; research-only dataset license)"
_PIPER_REPO = "MIT (rhasspy/piper-voices code and weights repository)"


@dataclass(frozen=True, slots=True)
class TtsModelEntry:
    """One installable synthesis model: identity, pinned archive and contents."""

    descriptor: ModelDescriptor
    family: str  # how the worker loads it: vits | kitten | kokoro
    archive_name: str
    url: str
    size_bytes: int
    sha256: str
    root: str  # the single top-level directory inside the archive
    files: tuple[tuple[str, str], ...]  # files to extract, under ``root``
    directories: tuple[tuple[str, str], ...]  # trees to extract, under ``root``
    languages: tuple[str, ...]
    voices: tuple[Voice, ...]
    sample_rate: int
    license: str
    ram_bytes: int  # measured peak of a synthesis process (V4-01)

    @property
    def model_id(self) -> str:
        return self.descriptor.model_id

    @property
    def name(self) -> str:
        """The archive file name (satisfies the downloader's ``PinnedArtifact``)."""
        return self.archive_name


def _descriptor(model_id: str, display_name: str) -> ModelDescriptor:
    return ModelDescriptor(
        provider_id=TTS_PROVIDER_ID,
        model_id=model_id,
        display_name=display_name,
        capabilities=frozenset({ModelCapability.SYNTHESIS, ModelCapability.CPU}),
    )


def _piper(
    *,
    voice: str,  # e.g. "es_MX-ald-medium"
    display_name: str,
    language: str,
    speaker: str,
    size_bytes: int,
    sha256: str,
    license: str,
    ram_mib: int,
) -> TtsModelEntry:
    root = f"vits-piper-{voice}"
    return TtsModelEntry(
        descriptor=_descriptor(f"piper-{voice}", display_name),
        family="vits",
        archive_name=f"{root}.tar.bz2",
        url=f"{_RELEASE}{root}.tar.bz2",
        size_bytes=size_bytes,
        sha256=sha256,
        root=root,
        files=(("model", f"{voice}.onnx"), ("tokens", "tokens.txt")),
        directories=(("data_dir", _ESPEAK_DIR),),
        languages=(language,),
        voices=(Voice("0", speaker, (language,)),),
        sample_rate=22_050,
        license=license,
        ram_bytes=ram_mib * _MIB,
    )


_KITTEN_VOICES = tuple(
    Voice(str(sid), f"expr-voice-{number}-{gender}", ("en",))
    for sid, (number, gender) in enumerate(
        (n, g) for n in (2, 3, 4, 5) for g in ("m", "f")
    )
)

# Kokoro multi-lang v1.0 speaker ids (sherpa-onnx order). ``ef_dora``=28,
# ``em_alex``=29 and ``em_santa``=53 were measured in V4-01; the English ids
# follow the same sorted order that lands ``ef_dora`` on 28.
_KOKORO_VOICES = (
    Voice("3", "af_heart", ("en",)),
    Voice("2", "af_bella", ("en",)),
    Voice("6", "af_nicole", ("en",)),
    Voice("9", "af_sarah", ("en",)),
    Voice("11", "am_adam", ("en",)),
    Voice("16", "am_michael", ("en",)),
    Voice("21", "bf_emma", ("en",)),
    Voice("26", "bm_george", ("en",)),
    Voice("28", "ef_dora", ("es",)),
    Voice("29", "em_alex", ("es",)),
    Voice("53", "em_santa", ("es",)),
)

TTS_CATALOG: tuple[TtsModelEntry, ...] = (
    _piper(
        voice="es_MX-ald-medium",
        display_name="Piper español (México) · ald",
        language="es",
        speaker="ald",
        size_bytes=67_196_497,
        sha256="c60cf7bc853eb01a875fba0756523fecf9d9f46c763b19785d223fc981fb4fb6",
        license=(
            f"{_PIPER_REPO}; ald dataset Unlicense; fine-tuned from davefx, "
            f"itself fine-tuned from lessac ({_LESSAC_NOTE}); {_ESPEAK_NOTE}"
        ),
        ram_mib=331,
    ),
    _piper(
        voice="es_ES-davefx-medium",
        display_name="Piper español (España) · davefx",
        language="es",
        speaker="davefx",
        size_bytes=67_184_952,
        sha256="a3f6beb54a9cb893279f72978a22f807a4d9fc9c7848157b524d5cc7b7f58b22",
        license=(
            f"{_PIPER_REPO}; davefx dataset CC0; fine-tuned from lessac "
            f"({_LESSAC_NOTE}); {_ESPEAK_NOTE}"
        ),
        ram_mib=307,
    ),
    _piper(
        voice="en_US-lessac-medium",
        display_name="Piper English (US) · lessac",
        language="en",
        speaker="lessac",
        size_bytes=67_230_653,
        sha256="9e3febfacf0abf4270172d2958bcec246032b7e88efc2720840cc80c93de334e",
        license=f"{_PIPER_REPO}; {_LESSAC_NOTE}; {_ESPEAK_NOTE}",
        ram_mib=300,
    ),
    TtsModelEntry(
        descriptor=_descriptor("kitten-nano-en-v0_8-int8", "KittenTTS nano English"),
        family="kitten",
        archive_name="kitten-nano-en-v0_8-int8.tar.bz2",
        url=f"{_RELEASE}kitten-nano-en-v0_8-int8.tar.bz2",
        size_bytes=31_220_690,
        sha256="6fa5be852612ce761094ba74ee6123b4fc4acfefa79bf64dc63acae4a83af2fd",
        root="kitten-nano-en-v0_8-int8",
        files=(
            ("model", "model.int8.onnx"),
            ("voices", "voices.bin"),
            ("tokens", "tokens.txt"),
        ),
        directories=(("data_dir", _ESPEAK_DIR),),
        languages=("en",),
        voices=_KITTEN_VOICES,
        sample_rate=24_000,
        license=f"Apache-2.0; {_ESPEAK_NOTE}",
        ram_bytes=234 * _MIB,
    ),
    TtsModelEntry(
        descriptor=_descriptor(
            "kokoro-int8-multi-lang-v1_0", "Kokoro multilingüe (calidad, lento)"
        ),
        family="kokoro",
        archive_name="kokoro-int8-multi-lang-v1_0.tar.bz2",
        url=f"{_RELEASE}kokoro-int8-multi-lang-v1_0.tar.bz2",
        size_bytes=132_303_094,
        sha256="4c3052abaa60943a341f193888cf6abd68787dae6ab8ae5c925a706caa247e4e",
        root="kokoro-int8-multi-lang-v1_0",
        files=(
            ("model", "model.int8.onnx"),
            ("voices", "voices.bin"),
            ("tokens", "tokens.txt"),
            ("lexicon_1", "lexicon-us-en.txt"),
            ("lexicon_2", "lexicon-zh.txt"),
        ),
        directories=(("data_dir", _ESPEAK_DIR),),
        languages=("en", "es", "fr", "hi", "it", "ja", "pt", "zh"),
        voices=_KOKORO_VOICES,
        sample_rate=24_000,
        license=f"Apache-2.0; {_ESPEAK_NOTE}",
        ram_bytes=470 * _MIB,
    ),
)


__all__ = [
    "DATA_DIR_MARKER",
    "NOTICE_FILES",
    "TTS_CATALOG",
    "TTS_PROVIDER_ID",
    "TTS_REQUIRES",
    "TtsModelEntry",
]
