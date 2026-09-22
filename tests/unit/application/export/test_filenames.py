"""Hostile regression tests for export filename sanitizing (S10.09)."""

from __future__ import annotations

import os.path

import pytest

from voz.application.export import safe_export_filename


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("entrevista", "entrevista.txt"),
        ("Mi Grabación 2026", "Mi Grabación 2026.txt"),
        ("../../etc/passwd", "passwd.txt"),
        ("..\\..\\Windows\\system32", "system32.txt"),
        ("/etc/shadow", "shadow.txt"),
        ("C:\\Users\\x\\secret", "secret.txt"),
        ("..", "transcript.txt"),
        ("...", "transcript.txt"),
        ("/", "transcript.txt"),
        ("", "transcript.txt"),
        ("   ", "transcript.txt"),
        (".hidden", "hidden.txt"),
        ("name\x00with\x00nul", "namewithnul.txt"),
        ("tab\tnew\nline\r", "tabnewline.txt"),
        ('quo"te<>:|?*', "quote.txt"),
        ("trailing dots...", "trailing dots.txt"),
        ("CON", "_CON.txt"),
        ("con", "_con.txt"),
        ("COM1.old", "_COM1.old.txt"),
        ("lpt9", "_lpt9.txt"),
        ("NUL", "_NUL.txt"),
        ("CONSOLE", "CONSOLE.txt"),
        ("archivo.final", "archivo.final.txt"),
    ],
)
def test_safe_export_filename_golden(stem: str, expected: str) -> None:
    assert safe_export_filename(stem, "txt") == expected


def test_stem_is_capped_at_100_characters() -> None:
    result = safe_export_filename("a" * 250, "md")

    assert result == "a" * 100 + ".md"


def test_cap_does_not_leave_trailing_dot_or_space() -> None:
    result = safe_export_filename("b" * 99 + ". tail", "md")

    assert result == "b" * 99 + ".md"


def test_extension_is_normalized() -> None:
    assert safe_export_filename("x", ".SRT") == "x.srt"


@pytest.mark.parametrize("extension", ["", ".", "../txt", "t xt", "a" * 17])
def test_hostile_extension_is_rejected(extension: str) -> None:
    with pytest.raises(ValueError, match="extension"):
        safe_export_filename("x", extension)


@pytest.mark.parametrize(
    "stem",
    [
        "../../../../../../etc/passwd",
        "..%2F..%2Fetc",
        "/absolute/path",
        "\\\\server\\share\\file",
        "a/../../b",
        "./../c",
        "x\x00/../../y",
        "\u2025\u2025/z",
    ],
)
def test_result_never_escapes_directory(stem: str) -> None:
    result = safe_export_filename(stem, "vtt")

    assert os.path.basename(result) == result
    assert not os.path.isabs(result)
    assert "/" not in result
    assert "\\" not in result
    assert result.rsplit(".", 1)[0] not in {"", ".", ".."}
    assert not result.startswith(".")
    assert result.endswith(".vtt")
