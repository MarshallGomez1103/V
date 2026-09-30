"""Provider key endpoints: no echo, no persistence outside the 0600 file, no logs."""

import logging
import sqlite3
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from voz.infrastructure.secrets import SECRETS_FILENAME, ProviderSecrets
from voz.interfaces.api.providers import create_providers_router

KEY = "sk-secret-value-987654321"


def _client(tmp_path: Path, **environ: str) -> httpx.Client:
    app = FastAPI()
    app.include_router(
        create_providers_router(
            ProviderSecrets(tmp_path / "voz", environ=environ),
            ("elevenlabs", "openai"),
        )
    )
    # TestClient is an httpx.Client; its own stubs resolve to Unknown under pyright.
    return cast(httpx.Client, TestClient(app))  # pyright: ignore[reportUnknownArgumentType]


def test_lists_providers_as_cloud_and_unconfigured(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/api/providers")
    assert response.status_code == 200
    assert response.json() == [
        {"id": "elevenlabs", "configured": False, "cloud": True},
        {"id": "openai", "configured": False, "cloud": True},
    ]


def test_put_then_get_then_delete_never_echoes_the_key(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    client = _client(tmp_path)
    put = client.put("/api/providers/openai/key", json={"key": KEY})
    assert put.status_code == 204
    assert put.content == b""
    listing = client.get("/api/providers")
    assert KEY not in listing.text
    assert {"id": "openai", "configured": True, "cloud": True} in listing.json()
    assert (tmp_path / "voz" / SECRETS_FILENAME).stat().st_mode & 0o777 == 0o600
    assert client.delete("/api/providers/openai/key").status_code == 204
    assert client.get("/api/providers").json()[1]["configured"] is False
    assert KEY not in caplog.text


def test_invalid_key_is_422_with_stable_code_and_no_echo(tmp_path: Path) -> None:
    bad = "has space " + KEY
    response = _client(tmp_path).put("/api/providers/openai/key", json={"key": bad})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "secrets_key_invalid"
    assert KEY not in response.text


def test_unknown_provider_is_404(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert client.put("/api/providers/nope/key", json={"key": KEY}).status_code == 404
    assert client.delete("/api/providers/nope/key").json()["detail"] == {
        "code": "provider_not_found",
        "message": "Unknown cloud provider.",
    }


def test_insecure_file_is_409_with_stable_code(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.put("/api/providers/openai/key", json={"key": KEY})
    (tmp_path / "voz" / SECRETS_FILENAME).chmod(0o644)
    response = client.put("/api/providers/openai/key", json={"key": KEY})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "secrets_file_insecure"
    assert str(tmp_path) not in response.text


def test_environment_key_counts_as_configured(tmp_path: Path) -> None:
    listing = _client(tmp_path, OPENAI_API_KEY=KEY).get("/api/providers").json()
    assert {"id": "openai", "configured": True, "cloud": True} in listing


def test_key_is_never_written_to_a_database(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.put("/api/providers/openai/key", json={"key": KEY})
    for database in tmp_path.rglob("*.sqlite*"):
        with sqlite3.connect(database) as connection:
            dump = "\n".join(connection.iterdump())
        assert KEY not in dump
    assert sorted(p.name for p in (tmp_path / "voz").iterdir()) == [SECRETS_FILENAME]


def test_estimate_endpoint_returns_dated_price_without_contacting_anyone(
    tmp_path: Path,
) -> None:
    from decimal import Decimal
    from uuid import UUID, uuid4

    from voz.application.estimate_cloud_cost import (
        CloudPrice,
        EstimateCloudTranscription,
    )
    from voz.domain.entities.media_asset import MediaAsset

    asset = MediaAsset(uuid4(), "0" * 64, "clase.wav", 10, duration_ms=300_000)

    class Assets:
        def get(self, media_asset_id: UUID) -> MediaAsset | None:
            return asset if media_asset_id == asset.id else None

    price = CloudPrice(Decimal("0.006"), "docs (no verificado en vivo)", "2026-09-30")
    app = FastAPI()
    app.include_router(
        create_providers_router(
            ProviderSecrets(tmp_path / "voz", environ={}),
            ("openai",),
            EstimateCloudTranscription(
                Assets(),  # type: ignore[arg-type]
                {("openai", "whisper-1"): price},
                {"openai": "whisper-1"},
            ),
        )
    )
    client = cast(httpx.Client, TestClient(app))  # pyright: ignore[reportUnknownArgumentType]
    ok = client.get(
        "/api/providers/openai/estimate", params={"media_asset_id": str(asset.id)}
    )
    assert ok.status_code == 200
    assert ok.json() == {
        "minutes": 5.0,
        "usd": 0.03,
        "price_source": "docs (no verificado en vivo)",
        "price_date": "2026-09-30",
    }
    missing = client.get(
        "/api/providers/openai/estimate", params={"media_asset_id": str(uuid4())}
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "media_not_found"
    assert (
        client.get(
            "/api/providers/nope/estimate", params={"media_asset_id": str(asset.id)}
        ).status_code
        == 404
    )
