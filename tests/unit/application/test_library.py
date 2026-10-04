"""Media type fallback for the library."""

from voz.application.library import media_type_or_guess


def test_probed_type_wins_and_the_extension_only_fills_gaps() -> None:
    assert media_type_or_guess("audio/ogg", "x.mp3") == "audio/ogg"
    assert media_type_or_guess(None, "clase.mp3") == "audio/mpeg"
    assert media_type_or_guess(None, "sin-extension") is None
    assert media_type_or_guess(None, None) is None
