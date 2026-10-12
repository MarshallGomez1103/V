import pytest

from voz.domain.entities import Voice


def test_voice_keeps_trimmed_id_name_and_languages() -> None:
    voice = Voice(id=" 3 ", name=" Ana ", languages=(" es ", "en"))

    assert (voice.id, voice.name, voice.languages) == ("3", "Ana", ("es", "en"))


def test_voice_languages_default_to_unknown() -> None:
    assert Voice(id="0", name="Default").languages == ()


@pytest.mark.parametrize(
    ("voice_id", "name"), [("", "Ana"), ("1", "  "), ("1", "a\nb")]
)
def test_voice_rejects_blank_or_control_text(voice_id: str, name: str) -> None:
    with pytest.raises(ValueError):
        Voice(id=voice_id, name=name)


def test_voice_rejects_non_tuple_blank_or_repeated_languages() -> None:
    with pytest.raises(TypeError):
        Voice(id="1", name="Ana", languages=["es"])  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Voice(id="1", name="Ana", languages=("es", " "))
    with pytest.raises(ValueError):
        Voice(id="1", name="Ana", languages=("es", " es"))
