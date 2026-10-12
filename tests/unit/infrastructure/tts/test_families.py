"""Family mapping, file validation and ONNX metadata, without sherpa-onnx."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from voz.domain.entities.voice import Voice
from voz.infrastructure.tts import families
from voz.infrastructure.tts.families import ModelFilesError


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _field(number: int, payload: bytes) -> bytes:
    return _varint(number << 3 | 2) + _varint(len(payload)) + payload


def onnx_bytes(metadata: dict[str, str]) -> bytes:
    """A minimal ModelProto: scalar fields, a big graph and metadata_props."""
    body = _varint(1 << 3 | 0) + _varint(8)  # ir_version (varint)
    body += _field(2, b"pytorch")  # producer_name
    body += _field(7, b"\x00" * 5000)  # graph: must be skipped, not parsed
    body += _varint(99 << 3 | 1) + b"\x01" * 8  # unknown fixed64
    body += _varint(98 << 3 | 5) + b"\x02" * 4  # unknown fixed32
    for key, value in metadata.items():
        entry = _field(1, key.encode()) + _field(2, value.encode())
        body += _field(14, entry)
    return body


def write_model(
    directory: Path, metadata: dict[str, str], name: str = "m.onnx"
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(onnx_bytes(metadata))
    return path


def make_dir(root: Path, *names: str, espeak: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name in names:
        (root / name).write_bytes(b"x")
    if espeak:
        (root / "espeak-ng-data").mkdir()
        (root / "espeak-ng-data" / "phontab").write_bytes(b"x")
    return root


# --- model_config ---------------------------------------------------------------


def test_vits_piper_uses_model_tokens_and_sibling_espeak(tmp_path: Path) -> None:
    root = make_dir(tmp_path, "v.onnx", "tokens.txt")

    spec = families.model_config(
        "vits", {"model": root / "v.onnx", "tokens": root / "tokens.txt"}
    )

    assert spec.field == "vits"
    assert spec.config_class == "OfflineTtsVitsModelConfig"
    assert dict(spec.kwargs) == {
        "model": str(root / "v.onnx"),
        "tokens": str(root / "tokens.txt"),
        "data_dir": str(root / "espeak-ng-data"),
    }


def test_piper_is_an_alias_of_vits(tmp_path: Path) -> None:
    root = make_dir(tmp_path, "v.onnx", "tokens.txt")

    spec = families.model_config(
        " Piper ", {"model": root / "v.onnx", "tokens": root / "tokens.txt"}
    )

    assert spec.field == "vits"


def test_vits_without_espeak_has_no_data_dir(tmp_path: Path) -> None:
    root = make_dir(tmp_path, "v.onnx", "tokens.txt", "lexicon.txt", espeak=False)

    spec = families.model_config(
        "vits",
        {
            "model": root / "v.onnx",
            "tokens": root / "tokens.txt",
            "lexicon": root / "lexicon.txt",
        },
    )

    assert "data_dir" not in spec.kwargs
    assert spec.kwargs["lexicon"] == str(root / "lexicon.txt")


def test_data_dir_given_as_a_file_inside_it_resolves_to_the_directory(
    tmp_path: Path,
) -> None:
    root = make_dir(tmp_path / "m", "v.onnx", "tokens.txt", espeak=False)
    shared = make_dir(tmp_path / "shared", espeak=True)

    spec = families.model_config(
        "kitten",
        {
            "model": root / "v.onnx",
            "voices": root / "tokens.txt",
            "tokens": root / "tokens.txt",
            "data_dir": shared / "espeak-ng-data" / "phontab",
        },
    )

    assert spec.kwargs["data_dir"] == str(shared / "espeak-ng-data")


def test_kitten_needs_voices_and_espeak(tmp_path: Path) -> None:
    root = make_dir(tmp_path, "model.int8.onnx", "voices.bin", "tokens.txt")
    files = {
        "model": root / "model.int8.onnx",
        "voices": root / "voices.bin",
        "tokens": root / "tokens.txt",
    }

    spec = families.model_config("kitten", files)

    assert spec.config_class == "OfflineTtsKittenModelConfig"
    assert set(spec.kwargs) == {"model", "voices", "tokens", "data_dir"}
    with pytest.raises(ModelFilesError, match="voices"):
        families.model_config(
            "kitten", {k: v for k, v in files.items() if k != "voices"}
        )


def test_kitten_without_espeak_is_not_installed(tmp_path: Path) -> None:
    root = make_dir(tmp_path, "m.onnx", "voices.bin", "tokens.txt", espeak=False)

    with pytest.raises(ModelFilesError, match="data_dir"):
        families.model_config(
            "kitten",
            {
                "model": root / "m.onnx",
                "voices": root / "voices.bin",
                "tokens": root / "tokens.txt",
            },
        )


def test_kokoro_joins_lexicons_in_key_order_and_sets_lang(tmp_path: Path) -> None:
    root = make_dir(
        tmp_path,
        "model.int8.onnx",
        "voices.bin",
        "tokens.txt",
        "lexicon-us-en.txt",
        "lexicon-zh.txt",
    )

    spec = families.model_config(
        "kokoro",
        {
            "model": root / "model.int8.onnx",
            "voices": root / "voices.bin",
            "tokens": root / "tokens.txt",
            "lexicon_2": root / "lexicon-zh.txt",
            "lexicon_1": root / "lexicon-us-en.txt",
        },
        lang="es",
    )

    assert spec.config_class == "OfflineTtsKokoroModelConfig"
    assert spec.kwargs["lexicon"] == (
        f"{root / 'lexicon-us-en.txt'},{root / 'lexicon-zh.txt'}"
    )
    assert spec.kwargs["lang"] == "es"
    assert "dict_dir" not in spec.kwargs  # V4-01: ignored since sherpa 1.12.15


def test_lang_is_only_for_kokoro(tmp_path: Path) -> None:
    root = make_dir(tmp_path, "v.onnx", "tokens.txt")

    spec = families.model_config(
        "vits", {"model": root / "v.onnx", "tokens": root / "tokens.txt"}, lang="es"
    )

    assert "lang" not in spec.kwargs


def test_matcha_uses_acoustic_model_and_vocoder(tmp_path: Path) -> None:
    root = make_dir(tmp_path, "am.onnx", "voc.onnx", "tokens.txt")

    spec = families.model_config(
        "matcha",
        {
            "acoustic_model": root / "am.onnx",
            "vocoder": root / "voc.onnx",
            "tokens": root / "tokens.txt",
        },
    )

    assert spec.field == "matcha"
    assert set(spec.kwargs) == {"acoustic_model", "vocoder", "tokens", "data_dir"}


def test_unknown_family_is_rejected() -> None:
    with pytest.raises(ModelFilesError, match="unsupported"):
        families.model_config("zipvoice", {})


def test_missing_required_file_entry_is_rejected(tmp_path: Path) -> None:
    root = make_dir(tmp_path, "v.onnx")

    with pytest.raises(ModelFilesError, match="tokens"):
        families.model_config("vits", {"model": root / "v.onnx"})


def test_file_absent_on_disk_is_rejected(tmp_path: Path) -> None:
    root = make_dir(tmp_path, "tokens.txt")

    with pytest.raises(ModelFilesError, match="model"):
        families.model_config(
            "vits", {"model": root / "gone.onnx", "tokens": root / "tokens.txt"}
        )


def test_missing_data_dir_path_is_rejected(tmp_path: Path) -> None:
    root = make_dir(tmp_path, "v.onnx", "tokens.txt")

    with pytest.raises(ModelFilesError, match="data_dir"):
        families.model_config(
            "vits",
            {
                "model": root / "v.onnx",
                "tokens": root / "tokens.txt",
                "data_dir": root / "nope" / "phontab",
            },
        )


def test_metadata_model_path_prefers_model_then_acoustic_model() -> None:
    assert families.metadata_model_path({"model": "a.onnx"}) == Path("a.onnx")
    assert families.metadata_model_path({"acoustic_model": "b.onnx"}) == Path("b.onnx")
    with pytest.raises(ModelFilesError):
        families.metadata_model_path({"tokens": "t"})


# --- discover_files -------------------------------------------------------------


def test_discover_piper_tarball_layout(tmp_path: Path) -> None:
    root = make_dir(tmp_path, "es_MX-ald-medium.onnx", "tokens.txt", "MODEL_CARD")
    (root / "es_MX-ald-medium.onnx.json").write_text("{}")

    files = families.discover_files("vits", root)

    assert files == {
        "model": root / "es_MX-ald-medium.onnx",
        "tokens": root / "tokens.txt",
        "data_dir": root / "espeak-ng-data" / "phontab",
    }


def test_discover_kokoro_takes_the_measured_lexicons_only(tmp_path: Path) -> None:
    root = make_dir(
        tmp_path,
        "model.int8.onnx",
        "voices.bin",
        "tokens.txt",
        "lexicon-us-en.txt",
        "lexicon-zh.txt",
        "lexicon-gb-en.txt",
    )

    files = families.discover_files("kokoro", root)

    assert files["voices"] == root / "voices.bin"
    lexicon = families.model_config("kokoro", files).kwargs["lexicon"]
    assert lexicon == f"{root / 'lexicon-us-en.txt'},{root / 'lexicon-zh.txt'}"


def test_discover_rejects_ambiguous_or_incomplete_dirs(tmp_path: Path) -> None:
    two = make_dir(tmp_path / "two", "a.onnx", "b.onnx", "tokens.txt")
    no_voices = make_dir(tmp_path / "kit", "m.onnx", "tokens.txt")

    with pytest.raises(ModelFilesError, match="one"):
        families.discover_files("vits", two)
    with pytest.raises(ModelFilesError, match="voices"):
        families.discover_files("kitten", no_voices)
    with pytest.raises(ModelFilesError, match="matcha"):
        families.discover_files("matcha", two)


# --- ONNX metadata and voices ------------------------------------------------------


def test_read_onnx_metadata_skips_the_graph(tmp_path: Path) -> None:
    path = write_model(tmp_path, {"n_speakers": "2", "speaker_names": "a,b"})

    assert families.read_onnx_metadata(path) == {
        "n_speakers": "2",
        "speaker_names": "a,b",
    }


def test_read_onnx_metadata_rejects_truncation(tmp_path: Path) -> None:
    path = tmp_path / "t.onnx"
    path.write_bytes(onnx_bytes({"k": "v"})[:-3])
    bad_varint = tmp_path / "v.onnx"
    bad_varint.write_bytes(b"\x80")

    with pytest.raises(ModelFilesError):
        families.read_onnx_metadata(path)
    with pytest.raises(ModelFilesError):
        families.read_onnx_metadata(bad_varint)


def test_speaker_names_from_list_or_id2speaker() -> None:
    assert families.speaker_names({"speaker_names": "x, y"}) == ("x", "y")
    mapping = json.dumps({"1": "b", "0": "a"})
    assert families.speaker_names({"id2speaker": mapping}) == ("a", "b")
    assert families.speaker_names({"id2speaker": '{"0": "a", "5": "b"}'}) == ()
    assert families.speaker_names({"id2speaker": "not json"}) == ()
    assert families.speaker_names({}) == ()


def test_speaker_count_uses_metadata_or_names() -> None:
    assert families.speaker_count({}) == 1
    assert families.speaker_count({"n_speakers": "8"}) == 8
    assert families.speaker_count({"n_speakers": "x", "speaker_names": "a,b"}) == 2


def test_resolve_sid_by_id_or_name() -> None:
    names = ("af_heart", "ef_dora")

    assert families.resolve_sid("1", names, 2) == 1
    assert families.resolve_sid("ef_dora", names, 2) == 1
    assert families.resolve_sid("2", names, 2) is None
    assert families.resolve_sid("nobody", names, 2) is None
    assert families.resolve_sid("-1", names, 2) is None
    assert families.resolve_sid(chr(0x661), (), 5) is None  # non-ASCII digit


def test_kokoro_lang_from_voice_prefix() -> None:
    assert families.kokoro_lang("ef_dora") == "es"
    assert families.kokoro_lang("af_heart") == "en-us"
    assert families.kokoro_lang("bm_george") == "en-gb"
    assert families.kokoro_lang("xx_unknown") == ""
    assert families.kokoro_lang("expr-voice-2-m") == ""


def test_read_voices_names_and_languages(tmp_path: Path) -> None:
    piper = write_model(tmp_path / "p", {"n_speakers": "1"})
    kitten = write_model(
        tmp_path / "k",
        {"n_speakers": "2", "speaker_names": "expr-voice-2-m,expr-voice-2-f"},
    )
    kokoro = write_model(
        tmp_path / "ko", {"n_speakers": "2", "speaker_names": "af_heart,ef_dora"}
    )

    (only,) = families.read_voices("vits", {"model": piper}, ("es",))
    assert (only.id, only.name, only.languages) == ("0", "Speaker 0", ("es",))
    assert [
        v.name for v in families.read_voices("kitten", {"model": kitten}, ("en",))
    ] == [
        "expr-voice-2-m",
        "expr-voice-2-f",
    ]
    voices = families.read_voices("kokoro", {"model": kokoro}, ("en", "es"))
    assert [(v.id, v.languages) for v in voices] == [("0", ("en",)), ("1", ("es",))]


def test_curated_names_back_up_an_onnx_without_speaker_names(tmp_path: Path) -> None:
    curated = (Voice("0", "ald", ("es",)),)
    for metadata in ({"n_speakers": "1"}, {"n_speakers": "1", "speaker_names": "0"}):
        model = write_model(tmp_path / str(len(metadata)), metadata)
        (voice,) = families.read_voices("vits", {"model": model}, ("xx",), curated)
        assert (voice.id, voice.name, voice.languages) == ("0", "ald", ("es",))
    generic = write_model(
        tmp_path / "g", {"n_speakers": "2", "speaker_names": "Speaker 0,Speaker_1"}
    )
    names = [
        v.name for v in families.read_voices("vits", {"model": generic}, (), curated)
    ]
    assert names == ["ald", "Speaker 1"]  # no curated voice for sid 1


def test_onnx_names_prevail_over_curated_ones(tmp_path: Path) -> None:
    model = write_model(tmp_path, {"n_speakers": "2", "speaker_names": "ana,luis"})
    curated = (Voice("0", "ald", ("es",)), Voice("1", "davefx", ("es",)))
    voices = families.read_voices("vits", {"model": model}, ("en",), curated)
    assert [(v.name, v.languages) for v in voices] == [
        ("ana", ("en",)),
        ("luis", ("en",)),
    ]


def test_read_voices_of_a_missing_model_is_model_files_error(tmp_path: Path) -> None:
    with pytest.raises(ModelFilesError):
        families.read_voices("vits", {"model": tmp_path / "gone.onnx"})
