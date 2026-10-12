from uuid import UUID

import pytest

from voz.domain.entities import SynthesizedAudio

JOB_ID = UUID("00000000-0000-0000-0000-000000000001")
SHA = "a" * 64


def make(**overrides: object) -> SynthesizedAudio:
    fields: dict[str, object] = {
        "job_id": JOB_ID,
        "relative_path": f"{JOB_ID}/audio.wav",
        "duration_ms": 1500,
        "sample_rate": 24_000,
        "chunk_count": 2,
        "sha256": SHA,
        "size_bytes": 72_044,
    }
    fields.update(overrides)
    return SynthesizedAudio(**fields)  # type: ignore[arg-type]


def test_valid_audio_keeps_its_metadata() -> None:
    audio = make()

    assert audio.relative_path == f"{JOB_ID}/audio.wav"
    assert (audio.duration_ms, audio.sample_rate, audio.chunk_count) == (
        1500,
        24_000,
        2,
    )


@pytest.mark.parametrize(
    "path",
    [
        "/home/user/audio.wav",
        "//server/share.wav",
        "../escape.wav",
        "job/../../escape.wav",
        "./audio.wav",
        "job//audio.wav",
        "C:/audio.wav",
        "job\\audio.wav",
        "",
        "job/a\x00.wav",
    ],
)
def test_path_must_be_relative_inside_storage(path: str) -> None:
    with pytest.raises(ValueError):
        make(relative_path=path)


@pytest.mark.parametrize(
    "name", ["duration_ms", "sample_rate", "chunk_count", "size_bytes"]
)
@pytest.mark.parametrize("value", [0, -1])
def test_counts_must_be_positive(name: str, value: int) -> None:
    with pytest.raises(ValueError):
        make(**{name: value})


@pytest.mark.parametrize("value", [1.5, True, "10"])
def test_counts_must_be_integers(value: object) -> None:
    with pytest.raises(TypeError):
        make(duration_ms=value)


@pytest.mark.parametrize("sha", ["A" * 64, "a" * 63, "g" * 64, "a" * 65, 123])
def test_sha256_must_be_lowercase_hex(sha: object) -> None:
    with pytest.raises(ValueError):
        make(sha256=sha)


def test_job_id_must_be_a_uuid() -> None:
    with pytest.raises(TypeError):
        make(job_id=str(JOB_ID))
