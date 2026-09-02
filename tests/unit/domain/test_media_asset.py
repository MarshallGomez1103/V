"""Tests for the MediaAsset domain entity."""

from dataclasses import fields
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest

from voz.domain.entities import MediaAsset

_DIGEST = "a" * 64


def test_media_asset_separates_entity_content_and_display_metadata() -> None:
    project_id = uuid4()
    asset = MediaAsset(
        project_id,
        _DIGEST,
        "  clase.webm  ",
        42_000,
        media_type="Audio/WebM",
        duration_ms=90_000,
    )

    assert isinstance(asset.id, UUID)
    assert asset.project_id == project_id
    assert asset.content_sha256 == _DIGEST
    assert asset.display_name == "clase.webm"
    assert asset.media_type == "audio/webm"
    assert asset.size_bytes == 42_000
    assert asset.duration_ms == 90_000
    assert asset.created_at.utcoffset() == timedelta(0)


def test_media_asset_domain_model_has_no_host_path_field() -> None:
    field_names = {item.name for item in fields(MediaAsset)}

    assert field_names.isdisjoint({"path", "source_path", "storage_path", "host_path"})


@pytest.mark.parametrize(
    "display_name",
    ["/home/student/clase.wav", "../clase.wav", r"C:\\audio\\clase.wav"],
)
def test_media_asset_rejects_path_like_display_names(display_name: str) -> None:
    with pytest.raises(ValueError, match="filename, not a path"):
        MediaAsset(uuid4(), _DIGEST, display_name, 1)


@pytest.mark.parametrize("digest", ["a" * 63, "A" * 64, "g" * 64])
def test_media_asset_rejects_invalid_content_digest(digest: str) -> None:
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        MediaAsset(uuid4(), digest, "clase.wav", 1)


@pytest.mark.parametrize("media_type", ["audio", "audio/", "/wav", "audio/wav/raw"])
def test_media_asset_rejects_invalid_media_type(media_type: str) -> None:
    with pytest.raises(ValueError, match="type/subtype"):
        MediaAsset(
            uuid4(),
            _DIGEST,
            "clase.wav",
            1,
            media_type=media_type,
        )


@pytest.mark.parametrize("size_bytes", [0, -1])
def test_media_asset_rejects_invalid_size(size_bytes: int) -> None:
    with pytest.raises(ValueError, match="size_bytes"):
        MediaAsset(uuid4(), _DIGEST, "clase.wav", size_bytes)


@pytest.mark.parametrize("size_bytes", [True, 1.5, "1"])
def test_media_asset_rejects_non_integer_size(size_bytes: object) -> None:
    with pytest.raises(TypeError, match="size_bytes"):
        MediaAsset(uuid4(), _DIGEST, "clase.wav", size_bytes)  # type: ignore[arg-type]


@pytest.mark.parametrize("duration_ms", [0, -1])
def test_media_asset_rejects_invalid_duration(duration_ms: int) -> None:
    with pytest.raises(ValueError, match="duration_ms"):
        MediaAsset(
            uuid4(),
            _DIGEST,
            "clase.wav",
            1,
            duration_ms=duration_ms,
        )


def test_media_asset_rejects_non_integer_duration() -> None:
    with pytest.raises(TypeError, match="duration_ms"):
        MediaAsset(
            uuid4(),
            _DIGEST,
            "clase.wav",
            1,
            duration_ms=True,
        )


def test_media_asset_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        MediaAsset(
            uuid4(),
            _DIGEST,
            "clase.wav",
            1,
            created_at=datetime(2026, 9, 2),
        )


def test_media_asset_rejects_non_uuid_project_identity() -> None:
    with pytest.raises(TypeError, match="project_id"):
        MediaAsset("project", _DIGEST, "clase.wav", 1)  # type: ignore[arg-type]
