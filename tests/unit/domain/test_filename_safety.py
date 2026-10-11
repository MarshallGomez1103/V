from __future__ import annotations

import pytest

from voz.domain.filename_safety import has_unsafe_filename_character


@pytest.mark.parametrize(
    "name",
    [
        "ok.wav",
        "reunión 録音.wav",
        "a b.mp3",
    ],
)
def test_plain_names_are_safe(name: str) -> None:
    assert has_unsafe_filename_character(name) is False


@pytest.mark.parametrize(
    "character",
    [
        "\x00",
        "\n",
        "​",  # zero-width space (Cf)
        "‪",  # LRE
        "‫",  # RLE
        "‬",  # PDF
        "‭",  # LRO
        "‮",  # RLO
        "⁦",  # LRI
        "⁧",  # RLI
        "⁨",  # FSI
        "⁩",  # PDI
    ],
)
def test_control_format_and_bidi_override_characters_are_unsafe(
    character: str,
) -> None:
    assert has_unsafe_filename_character(f"a{character}b.wav") is True
