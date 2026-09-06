"""Tests for path-free, safe reopening of normalized inference audio."""

import wave
from pathlib import Path
from uuid import uuid4

import pytest

from voz.application.ports.inference_audio import (
    InferenceAudioError,
    InferenceAudioFailureCode,
)
from voz.application.ports.transcription import TranscriptionClip
from voz.infrastructure.inference_audio import FileSystemInferenceAudioSource


def _source(tmp_path: Path) -> tuple[FileSystemInferenceAudioSource, Path]:
    project_id = uuid4()
    media_asset_id = uuid4()
    derivative = (
        tmp_path
        / "projects"
        / str(project_id)
        / "derivatives"
        / f"{media_asset_id}.inference.wav"
    )
    return (
        FileSystemInferenceAudioSource(tmp_path, project_id, media_asset_id),
        derivative,
    )


def test_opens_normalized_audio_without_returning_its_path(tmp_path: Path) -> None:
    source, derivative = _source(tmp_path)
    derivative.parent.mkdir(parents=True)
    derivative.write_bytes(b"RIFF-normalized")

    with source.open() as audio:
        assert audio.read() == b"RIFF-normalized"
        assert not isinstance(audio, Path)


def test_maps_missing_audio_to_a_stable_error(tmp_path: Path) -> None:
    source, derivative = _source(tmp_path)

    with pytest.raises(InferenceAudioError) as raised:
        source.open()

    assert raised.value.code is InferenceAudioFailureCode.NOT_FOUND
    assert str(derivative) not in raised.value.user_message


def test_rejects_symlinked_derivative(tmp_path: Path) -> None:
    source, derivative = _source(tmp_path)
    private_file = tmp_path / "private.wav"
    private_file.write_bytes(b"private")
    derivative.parent.mkdir(parents=True)
    derivative.symlink_to(private_file)

    with pytest.raises(InferenceAudioError) as raised:
        source.open()

    assert raised.value.code is InferenceAudioFailureCode.UNSAFE_STORAGE_PATH
    assert str(private_file) not in raised.value.user_message


def test_opens_only_the_requested_pcm_clip(tmp_path: Path) -> None:
    source, derivative = _source(tmp_path)
    derivative.parent.mkdir(parents=True)
    with wave.open(str(derivative), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        output.writeframes(b"\x00\x00" * 16_000)

    with (
        source.open(TranscriptionClip(250, 500)) as audio,
        wave.open(audio, "rb") as clipped,
    ):
        assert clipped.getnchannels() == 1
        assert clipped.getsampwidth() == 2
        assert clipped.getframerate() == 16_000
        assert clipped.getnframes() == 4_000
