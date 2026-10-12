"""Tests for the synthesis audio filesystem storage (V3-04)."""

from __future__ import annotations

import hashlib
import os
import struct
import wave
from array import array
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from voz.application.ports.speech_synthesis import PcmAudio, PcmSampleFormat
from voz.application.ports.synthesis_audio_storage import (
    SynthesisAudioStorage,
    SynthesisStorageError,
    SynthesisStorageErrorCode,
)
from voz.infrastructure.synthesis_storage import FileSystemSynthesisStorage

RATE = 16_000
Code = SynthesisStorageErrorCode


def _int16(values: list[int], rate: int = RATE) -> PcmAudio:
    return PcmAudio(struct.pack(f"<{len(values)}h", *values), rate)


def _float32(values: list[float], rate: int = RATE) -> PcmAudio:
    return PcmAudio(
        struct.pack(f"<{len(values)}f", *values), rate, PcmSampleFormat.FLOAT32
    )


def _read_wav(path: Path) -> tuple[wave._wave_params, list[int]]:  # pyright: ignore[reportPrivateUsage]
    with wave.open(str(path), "rb") as reader:
        params = reader.getparams()
        frames = reader.readframes(params.nframes)
    return params, list(array("h", frames))


@pytest.fixture
def storage(tmp_path: Path, platform_mode: str) -> FileSystemSynthesisStorage:
    assert platform_mode
    return FileSystemSynthesisStorage(tmp_path / "data")


def test_adapter_satisfies_port(storage: FileSystemSynthesisStorage) -> None:
    assert isinstance(storage, SynthesisAudioStorage)


def test_writes_valid_wav_with_silences_between_chunks(
    tmp_path: Path, storage: FileSystemSynthesisStorage
) -> None:
    job_id = uuid4()
    first = _int16([1, 2, 3, 4] * 400)  # 1600 frames = 100 ms
    second = _int16([-5, 6] * 800)  # 1600 frames = 100 ms

    result = storage.write(job_id, [first, second], [250])

    assert result.relative_path == f"synthesis/{job_id}/audio.wav"
    assert result.job_id == job_id
    assert result.sample_rate == RATE
    assert result.chunk_count == 2
    assert result.duration_ms == 100 + 250 + 100
    params, samples = _read_wav(tmp_path / "data" / result.relative_path)
    assert (params.nchannels, params.sampwidth, params.framerate) == (1, 2, RATE)
    assert params.nframes == 1600 + 4000 + 1600
    assert samples[:1600] == [1, 2, 3, 4] * 400
    assert set(samples[1600:5600]) == {0}
    assert samples[5600:] == [-5, 6] * 800


def test_sha256_and_size_describe_the_stored_file(
    tmp_path: Path, storage: FileSystemSynthesisStorage
) -> None:
    result = storage.write(uuid4(), [_int16([7] * 100)], [])

    stored = (tmp_path / "data" / result.relative_path).read_bytes()
    assert result.sha256 == hashlib.sha256(stored).hexdigest()
    assert result.size_bytes == len(stored) == 44 + 200
    with storage.open_for_reading(result.relative_path) as handle:
        assert handle.read() == stored


def test_float32_is_converted_with_saturation(
    tmp_path: Path, storage: FileSystemSynthesisStorage
) -> None:
    result = storage.write(
        uuid4(),
        [_float32([0.0, 0.5, -0.5, 1.0, -1.0, 3.5, -7.0, float("inf"), float("nan")])],
        [],
    )

    _, samples = _read_wav(tmp_path / "data" / result.relative_path)
    assert samples == [0, 16384, -16384, 32767, -32768, 32767, -32768, 32767, 0]


def test_int16_extremes_pass_through_untouched(
    tmp_path: Path, storage: FileSystemSynthesisStorage
) -> None:
    result = storage.write(uuid4(), [_int16([32767, -32768, 0])], [])

    _, samples = _read_wav(tmp_path / "data" / result.relative_path)
    assert samples == [32767, -32768, 0]


def test_mixed_sample_formats_join_in_order(
    tmp_path: Path, storage: FileSystemSynthesisStorage
) -> None:
    result = storage.write(uuid4(), [_float32([0.5]), _int16([9])], [0])

    _, samples = _read_wav(tmp_path / "data" / result.relative_path)
    assert samples == [16384, 9]


def test_different_sample_rates_are_rejected_before_any_io(
    tmp_path: Path, storage: FileSystemSynthesisStorage
) -> None:
    with pytest.raises(SynthesisStorageError) as caught:
        storage.write(uuid4(), [_int16([1]), _int16([1], rate=22_050)], [10])

    assert caught.value.code is Code.SAMPLE_RATE_MISMATCH
    assert not (tmp_path / "data").exists()


def test_no_chunks_is_a_typed_error(storage: FileSystemSynthesisStorage) -> None:
    with pytest.raises(SynthesisStorageError) as caught:
        storage.write(uuid4(), [], [])

    assert caught.value.code is Code.NO_AUDIO


@pytest.mark.parametrize("gaps", [[], [1, 2], [-1]])
def test_gap_count_and_sign_are_validated(
    storage: FileSystemSynthesisStorage, gaps: list[int]
) -> None:
    with pytest.raises(ValueError, match="gaps_ms"):
        storage.write(uuid4(), [_int16([1]), _int16([2])], gaps)


def test_never_overwrites_an_existing_audio(
    tmp_path: Path, storage: FileSystemSynthesisStorage
) -> None:
    job_id = uuid4()
    first = storage.write(job_id, [_int16([1] * 50)], [])
    path = tmp_path / "data" / first.relative_path
    original = path.read_bytes()

    with pytest.raises(SynthesisStorageError) as caught:
        storage.write(job_id, [_int16([2] * 80)], [])

    assert caught.value.code is Code.AUDIO_EXISTS
    assert path.read_bytes() == original
    assert [p.name for p in path.parent.iterdir()] == ["audio.wav"]


def test_stored_audio_is_read_only_and_leaves_no_temporaries(
    tmp_path: Path, storage: FileSystemSynthesisStorage
) -> None:
    result = storage.write(uuid4(), [_int16([1] * 50)], [])

    path = tmp_path / "data" / result.relative_path
    assert os.stat(path).st_mode & 0o222 == 0
    assert [p.name for p in path.parent.iterdir()] == ["audio.wav"]


def test_open_for_reading_is_seekable_for_ranges(
    storage: FileSystemSynthesisStorage,
) -> None:
    result = storage.write(uuid4(), [_int16(list(range(100)))], [])

    with storage.open_for_reading(result.relative_path) as handle:
        handle.seek(44 + 2)
        assert handle.read(4) == struct.pack("<2h", 1, 2)
        assert handle.seekable()


def test_open_for_reading_missing_and_invalid_paths(
    storage: FileSystemSynthesisStorage,
) -> None:
    with pytest.raises(SynthesisStorageError) as missing:
        storage.open_for_reading(f"synthesis/{uuid4()}/audio.wav")
    assert missing.value.code is Code.AUDIO_NOT_FOUND

    storage.write(uuid4(), [_int16([1])], [])
    with pytest.raises(SynthesisStorageError) as missing_file:
        storage.open_for_reading(f"synthesis/{uuid4()}/audio.wav")
    assert missing_file.value.code is Code.AUDIO_NOT_FOUND


@pytest.mark.parametrize(
    "path",
    [
        "",
        "audio.wav",
        "/etc/passwd",
        "synthesis/../audio.wav",
        "synthesis/not-a-uuid/audio.wav",
        "synthesis/00000000000000000000000000000001/audio.wav",
        f"synthesis/{uuid4()}/other.wav",
        f"synthesis/{uuid4()}/audio.wav/extra",
        f"synthesis\\{uuid4()}\\audio.wav",
        f"other/{uuid4()}/audio.wav",
    ],
)
def test_invalid_relative_paths_are_rejected(
    storage: FileSystemSynthesisStorage, path: str
) -> None:
    with pytest.raises(SynthesisStorageError) as opened:
        storage.open_for_reading(path)
    with pytest.raises(SynthesisStorageError) as deleted:
        storage.delete(path)

    assert opened.value.code is Code.INVALID_PATH
    assert deleted.value.code is Code.INVALID_PATH


def test_delete_removes_only_that_job_and_is_idempotent(
    tmp_path: Path, storage: FileSystemSynthesisStorage
) -> None:
    keep = storage.write(uuid4(), [_int16([1] * 10)], [])
    gone = storage.write(uuid4(), [_int16([2] * 10)], [])

    storage.delete(gone.relative_path)
    storage.delete(gone.relative_path)

    assert not (tmp_path / "data" / gone.relative_path).parent.exists()
    assert (tmp_path / "data" / keep.relative_path).is_file()


def test_delete_without_any_storage_is_a_noop(
    storage: FileSystemSynthesisStorage,
) -> None:
    storage.delete(f"synthesis/{uuid4()}/audio.wav")


def test_a_deleted_job_can_be_written_again(
    storage: FileSystemSynthesisStorage,
) -> None:
    job_id = uuid4()
    first = storage.write(job_id, [_int16([1] * 10)], [])
    storage.delete(first.relative_path)

    again = storage.write(job_id, [_int16([2] * 10)], [])

    assert again.relative_path == first.relative_path
    assert again.sha256 != first.sha256


def test_delete_unlinks_symlinks_without_touching_their_targets(
    tmp_path: Path, storage: FileSystemSynthesisStorage
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("keep me")
    job_id = uuid4()
    job_dir = tmp_path / "data" / "synthesis" / str(job_id)
    job_dir.mkdir(parents=True)
    (job_dir / "audio.wav").symlink_to(secret)
    (job_dir / "evil").symlink_to(outside, target_is_directory=True)

    storage.delete(f"synthesis/{job_id}/audio.wav")

    assert not job_dir.exists()
    assert secret.read_text() == "keep me"


def test_delete_refuses_a_job_directory_that_is_a_symlink(
    tmp_path: Path, storage: FileSystemSynthesisStorage
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "audio.wav").write_bytes(b"precious")
    job_id = uuid4()
    synthesis = tmp_path / "data" / "synthesis"
    synthesis.mkdir(parents=True)
    (synthesis / str(job_id)).symlink_to(outside, target_is_directory=True)

    with pytest.raises(SynthesisStorageError) as caught:
        storage.delete(f"synthesis/{job_id}/audio.wav")

    assert caught.value.code is Code.UNSAFE_STORAGE_PATH
    assert (outside / "audio.wav").read_bytes() == b"precious"


def test_delete_job_removes_leftovers_idempotently_and_allows_a_rewrite(
    tmp_path: Path, storage: FileSystemSynthesisStorage
) -> None:
    keep = storage.write(uuid4(), [_int16([1] * 10)], [])
    orphan = storage.write(uuid4(), [_int16([2] * 10)], [])
    job_id = UUID(orphan.relative_path.split("/")[1])
    unrecorded = uuid4()

    storage.delete_job(job_id)
    storage.delete_job(job_id)
    storage.delete_job(unrecorded)  # never written: nothing to do

    assert not (tmp_path / "data" / orphan.relative_path).parent.exists()
    assert (tmp_path / "data" / keep.relative_path).is_file()
    assert storage.write(job_id, [_int16([3] * 10)], []).sha256 != orphan.sha256


def test_delete_job_unlinks_symlinks_without_touching_their_targets(
    tmp_path: Path, storage: FileSystemSynthesisStorage
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("keep me")
    job_id = uuid4()
    job_dir = tmp_path / "data" / "synthesis" / str(job_id)
    job_dir.mkdir(parents=True)
    (job_dir / "audio.wav").symlink_to(secret)
    (job_dir / "evil").symlink_to(outside, target_is_directory=True)

    storage.delete_job(job_id)

    assert not job_dir.exists()
    assert secret.read_text() == "keep me"


def test_delete_job_refuses_a_job_directory_that_is_a_symlink(
    tmp_path: Path, storage: FileSystemSynthesisStorage
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "audio.wav").write_bytes(b"precious")
    job_id = uuid4()
    synthesis = tmp_path / "data" / "synthesis"
    synthesis.mkdir(parents=True)
    (synthesis / str(job_id)).symlink_to(outside, target_is_directory=True)

    with pytest.raises(SynthesisStorageError) as caught:
        storage.delete_job(job_id)

    assert caught.value.code is Code.UNSAFE_STORAGE_PATH
    assert (outside / "audio.wav").read_bytes() == b"precious"


def test_read_and_write_refuse_symlinked_audio_and_job_directory(
    tmp_path: Path, storage: FileSystemSynthesisStorage
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "audio.wav").write_bytes(b"precious")
    linked_dir_job, linked_file_job = uuid4(), uuid4()
    synthesis = tmp_path / "data" / "synthesis"
    synthesis.mkdir(parents=True)
    (synthesis / str(linked_dir_job)).symlink_to(outside, target_is_directory=True)
    file_job_dir = synthesis / str(linked_file_job)
    file_job_dir.mkdir()
    (file_job_dir / "audio.wav").symlink_to(outside / "audio.wav")

    for job_id in (linked_dir_job, linked_file_job):
        with pytest.raises(SynthesisStorageError) as read:
            storage.open_for_reading(f"synthesis/{job_id}/audio.wav")
        assert read.value.code is Code.UNSAFE_STORAGE_PATH
    with pytest.raises(SynthesisStorageError) as written_dir:
        storage.write(linked_dir_job, [_int16([1])], [])
    with pytest.raises(SynthesisStorageError) as written_file:
        storage.write(linked_file_job, [_int16([1])], [])

    assert written_dir.value.code is Code.UNSAFE_STORAGE_PATH
    assert written_file.value.code is Code.AUDIO_EXISTS
    assert (outside / "audio.wav").read_bytes() == b"precious"
    assert [p.name for p in outside.iterdir()] == ["audio.wav"]


def test_failed_write_leaves_no_residue(
    tmp_path: Path,
    storage: FileSystemSynthesisStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "fsync", explode)

    with pytest.raises(SynthesisStorageError) as caught:
        storage.write(uuid4(), [_int16([1] * 10)], [])

    assert caught.value.code is Code.IO_ERROR
    assert list((tmp_path / "data" / "synthesis").iterdir()) == []


def test_unsafe_storage_root_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(SynthesisStorageError) as caught:
        FileSystemSynthesisStorage(link).write(uuid4(), [_int16([1])], [])

    assert caught.value.code is Code.UNSAFE_STORAGE_PATH
    assert list(real.iterdir()) == []
