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
        "piper-es_ES-davefx-medium",
        "piper-en_US-lessac-medium",
        "kitten-nano-en-v0_8-int8",
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
        "calidad, lento"
        in _BY_ID["kokoro-int8-multi-lang-v1_0"].descriptor.display_name
    )
    assert "lento" not in _BY_ID["kitten-nano-en-v0_8-int8"].descriptor.display_name


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
    assert [v.name for v in _BY_ID["piper-es_MX-ald-medium"].voices] == ["ald"]
