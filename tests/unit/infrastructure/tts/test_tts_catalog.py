"""The pinned TTS catalog: identity, integrity pins and honest licenses."""

from __future__ import annotations

import re

import pytest

from voz.application.ports.model_installation import ModelFile
from voz.domain.entities.model_descriptor import ModelCapability
from voz.infrastructure.tts.catalog import TTS_CATALOG, TTS_PROVIDER_ID, TtsModelEntry

_BY_ID = {entry.model_id: entry for entry in TTS_CATALOG}
_RELEASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"


def test_the_catalog_has_the_measured_models_with_exact_pins() -> None:
    assert set(_BY_ID) == {
        "piper-es_MX-ald-medium",
        "piper-es_MX-claude-high-int8",
        "piper-es_ES-davefx-medium",
        "piper-en_US-lessac-medium",
        "kitten-nano-en-v0_8-int8",
        "kitten-mini-en-v0_8",
        "kokoro-int8-multi-lang-v1_0",
    }
    assert TTS_PROVIDER_ID == "sherpa-onnx-tts"
    ald = _BY_ID["piper-es_MX-ald-medium"]
    assert (ald.size_bytes, ald.sha256) == (
        67_196_497,
        "c60cf7bc853eb01a875fba0756523fecf9d9f46c763b19785d223fc981fb4fb6",
    )
    assert _BY_ID["kokoro-int8-multi-lang-v1_0"].size_bytes == 132_303_094
    assert _BY_ID["kitten-nano-en-v0_8-int8"].sha256 == (
        "6fa5be852612ce761094ba74ee6123b4fc4acfefa79bf64dc63acae4a83af2fd"
    )


@pytest.mark.parametrize("entry", TTS_CATALOG, ids=lambda e: e.model_id)
def test_each_entry_is_well_formed(entry: TtsModelEntry) -> None:
    assert entry.descriptor.provider_id == TTS_PROVIDER_ID
    assert entry.descriptor.capabilities == {
        ModelCapability.SYNTHESIS,
        ModelCapability.CPU,
    }
    assert entry.url == f"{_RELEASE}{entry.archive_name}"
    assert entry.archive_name.endswith(".tar.bz2") and entry.root in entry.archive_name
    assert re.fullmatch(r"[0-9a-f]{64}", entry.sha256)
    ModelFile(entry.archive_name, entry.size_bytes, entry.sha256)  # validates
    assert dict(entry.directories) == {"data_dir": "espeak-ng-data"}
    assert {"model", "tokens"} <= {key for key, _ in entry.files}
    paths = [rel for _, rel in (*entry.files, *entry.directories)]
    assert len(set(paths)) == len(paths)
    assert all(not rel.startswith("/") and ".." not in rel for rel in paths)
    ids = [voice.id for voice in entry.voices]
    assert len(set(ids)) == len(ids) and all(i.isdecimal() for i in ids)
    assert {lang for v in entry.voices for lang in v.languages} <= set(entry.languages)
    assert entry.sample_rate in {22_050, 24_000} and entry.ram_bytes > 0
    assert "GPL-3.0" in entry.license  # espeak-ng-data ships inside every archive


def test_piper_licenses_do_not_hide_the_lessac_dataset_restriction() -> None:
    for model_id in (
        "piper-en_US-lessac-medium",
        "piper-es_ES-davefx-medium",
        "piper-es_MX-ald-medium",
    ):
        license_text = _BY_ID[model_id].license
        assert "MIT" in license_text and "lessac" in license_text
        assert "research-only dataset license" in license_text
    assert "CC0" in _BY_ID["piper-es_ES-davefx-medium"].license
    assert "Unlicense" in _BY_ID["piper-es_MX-ald-medium"].license


def test_kitten_and_kokoro_are_apache_and_kokoro_is_marked_slow() -> None:
    for model_id in ("kitten-nano-en-v0_8-int8", "kokoro-int8-multi-lang-v1_0"):
        assert _BY_ID[model_id].license.startswith("Apache-2.0")
    assert (
        "quality, slow" in _BY_ID["kokoro-int8-multi-lang-v1_0"].descriptor.display_name
    )
    assert "slow" not in _BY_ID["kitten-nano-en-v0_8-int8"].descriptor.display_name


def test_display_names_are_neutral_english_whatever_the_ui_language() -> None:
    """Like the Whisper entries: no Spanish words or accents in what the UI shows."""
    spanish = re.compile(r"[áéíóúñü]|\b(español|México|España|calidad|lento)\b", re.I)
    for entry in TTS_CATALOG:
        assert not spanish.search(entry.descriptor.display_name), entry.model_id


def test_voices_follow_the_measured_speaker_ids() -> None:
    kokoro = {v.name: v.id for v in _BY_ID["kokoro-int8-multi-lang-v1_0"].voices}
    assert (kokoro["ef_dora"], kokoro["em_alex"], kokoro["em_santa"]) == (
        "28",
        "29",
        "53",
    )
    kitten = _BY_ID["kitten-nano-en-v0_8-int8"].voices
    assert [v.id for v in kitten] == [str(i) for i in range(8)]
    assert kitten[0].name == "expr-voice-2-m" and kitten[7].name == "expr-voice-5-f"
    for model_id, name in (
        ("piper-es_MX-ald-medium", "ald"),
        ("piper-es_ES-davefx-medium", "davefx"),
        ("piper-en_US-lessac-medium", "lessac"),
    ):
        assert [(v.id, v.name) for v in _BY_ID[model_id].voices] == [("0", name)]


def test_claude_int8_pins_archive_and_preserves_the_internal_model_name() -> None:
    entry = _BY_ID["piper-es_MX-claude-high-int8"]
    assert (entry.archive_name, entry.root) == (
        "vits-piper-es_MX-claude-high-int8.tar.bz2",
        "vits-piper-es_MX-claude-high-int8",
    )
    assert (entry.size_bytes, entry.sha256) == (
        21_216_685,
        "0f9fc9c07d2e17bdc0f5f33a657addae92085da85704cb86a861e59d32f3bbfa",
    )
    assert dict(entry.files) == {
        "model": "es_MX-claude-high.onnx",
        "tokens": "tokens.txt",
    }
    assert [(v.id, v.name, v.languages) for v in entry.voices] == [
        ("0", "claude", ("es",))
    ]
    assert "claude dataset Apache-2.0" in entry.license
    assert "lessac" not in entry.license


def test_kitten_mini_uses_the_measured_archive_layout_and_speaker_ids() -> None:
    entry = _BY_ID["kitten-mini-en-v0_8"]
    assert (entry.size_bytes, entry.sha256) == (
        67_547_594,
        "518f9b130320f690d5b5476df77bde4215fca67773cda16710318e5081234b9d",
    )
    assert dict(entry.files) == {
        "model": "model.onnx",
        "voices": "voices.bin",
        "tokens": "tokens.txt",
    }
    assert entry.voices == _BY_ID["kitten-nano-en-v0_8-int8"].voices
    assert entry.license.startswith("Apache-2.0")
