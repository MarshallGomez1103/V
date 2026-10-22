"""Provider key endpoints: no echo, no persistence outside the 0600 file, no logs."""

import logging
import sqlite3
import stat
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from voz.application.ports.cloud_providers import CloudProviderInfo
from voz.application.ports.compatible_endpoints import (
    CompatibleEndpoint,
    ConnectionCheck,
)
from voz.infrastructure.cloud.compatible_store import (
    ENDPOINTS_FILENAME,
    FileCompatibleEndpointStore,
)
from voz.infrastructure.cloud.provider_info import CLOUD_PROVIDER_INFO
from voz.infrastructure.secrets import SECRETS_FILENAME, ProviderSecrets
from voz.interfaces.api.providers import create_providers_router

KEY = "sk-secret-value-987654321"


def _client(tmp_path: Path, **environ: str) -> httpx.Client:
    app = FastAPI()
    app.include_router(
        create_providers_router(
            ProviderSecrets(tmp_path / "voz", environ=environ),
            CLOUD_PROVIDER_INFO,
        )
    )
    # TestClient is an httpx.Client; its own stubs resolve to Unknown under pyright.
    return cast(httpx.Client, TestClient(app))  # pyright: ignore[reportUnknownArgumentType]


def test_lists_providers_as_cloud_and_unconfigured(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/api/providers")
    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "openai",
            "label": "OpenAI",
            "privacy_url": "https://openai.com/policies/privacy-policy",
            "configured": False,
            "cloud": True,
        },
        {
            "id": "elevenlabs",
            "label": "ElevenLabs",
            "privacy_url": "https://elevenlabs.io/privacy",
            "configured": False,
            "cloud": True,
        },
    ]


def test_lists_whatever_providers_the_composition_root_gives(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(
        create_providers_router(
            ProviderSecrets(tmp_path / "voz", environ={}),
            (
                CloudProviderInfo("acme", "Acme Cloud", "https://acme.example/privacy"),
                "bare",
            ),
        )
    )
    client = cast(httpx.Client, TestClient(app))  # pyright: ignore[reportUnknownArgumentType]
    assert [
        (p["id"], p["label"], p["privacy_url"])
        for p in client.get("/api/providers").json()
    ] == [
        ("acme", "Acme Cloud", "https://acme.example/privacy"),
        ("bare", "bare", None),
    ]
    assert client.put("/api/providers/acme/key", json={"key": "k"}).status_code == 204
    assert client.put("/api/providers/nope/key", json={"key": "k"}).status_code == 404


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
    assert any(p["id"] == "openai" and p["configured"] for p in listing.json())
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
    assert [(p["id"], p["configured"]) for p in listing] == [
        ("openai", True),
        ("elevenlabs", False),
    ]


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


# --- OpenAI-compatible endpoints (V4-04) ------------------------------------------


class _Tester:
    def __init__(self) -> None:
        self.keys: list[str | None] = []

    def check(self, endpoint: CompatibleEndpoint, key: str | None) -> ConnectionCheck:
        self.keys.append(key)
        return ConnectionCheck(True, 200, ("m1",))


def _endpoints_client(tmp_path: Path, tester: _Tester | None = None) -> httpx.Client:
    config = tmp_path / "voz"
    app = FastAPI()
    app.include_router(
        create_providers_router(
            ProviderSecrets(config, environ={}),
            CLOUD_PROVIDER_INFO,
            endpoints=FileCompatibleEndpointStore(config),
            tester=tester,
        )
    )
    return cast(httpx.Client, TestClient(app))  # pyright: ignore[reportUnknownArgumentType]


def _endpoint_body(**changes: object) -> dict[str, object]:
    return {
        "name": "Speaches",
        "base_url": "http://127.0.0.1:8000/v1",
        "key": KEY,
        "stt_models": ["Systran/faster-whisper-small"],
        **changes,
    }


def test_compatible_endpoint_key_goes_to_secrets_and_is_never_echoed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    tester = _Tester()
    client = _endpoints_client(tmp_path, tester)

    created = client.post("/api/providers/compatible", json=_endpoint_body())
    endpoint_id = created.json()["id"]
    tested = client.post(f"/api/providers/compatible/{endpoint_id}/test")

    assert created.status_code == 201 and tested.json()["models"] == ["m1"]
    assert tester.keys == [KEY]
    for response in (created, tested, client.get("/api/providers/compatible")):
        assert KEY not in response.text
    assert KEY not in (tmp_path / "voz" / "openai-compatible.json").read_text()
    assert KEY in (tmp_path / "voz" / SECRETS_FILENAME).read_text()
    assert KEY not in caplog.text

    cleared = client.put(
        f"/api/providers/compatible/{endpoint_id}",
        json=_endpoint_body(key=None, clear_key=True),
    )
    assert cleared.json()["key_configured"] is False


def test_compatible_endpoint_errors_are_stable(tmp_path: Path) -> None:
    client = _endpoints_client(tmp_path)
    created = client.post("/api/providers/compatible", json=_endpoint_body()).json()
    url = f"/api/providers/compatible/{created['id']}"

    def code(response: httpx.Response) -> tuple[int, str]:
        return response.status_code, response.json()["detail"]["code"]

    assert code(client.post(url + "/test")) == (501, "endpoint_test_unavailable")
    assert code(client.delete(url)) == (403, "endpoint_delete_forbidden")
    assert code(
        client.put("/api/providers/compatible/aaaaaaaaaaaa", json=_endpoint_body())
    ) == (404, "endpoint_not_found")
    assert code(
        client.post(
            "/api/providers/compatible", json=_endpoint_body(base_url="file:///x")
        )
    ) == (422, "endpoint_invalid")
    assert code(
        client.post("/api/providers/compatible", json=_endpoint_body(key="has space"))
    ) == (422, "secrets_key_invalid")
    (tmp_path / "voz" / "openai-compatible.json").chmod(0o644)
    assert code(client.get("/api/providers/compatible")) == (
        409,
        "endpoints_file_insecure",
    )


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.example.com/v1",
        "https://192.168.1.20:8000/v1",
        "https://localhost.example.com/v1",
    ],
)
def test_cloud_consent_is_required_before_saving_or_testing(
    tmp_path: Path, base_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    tester = _Tester()
    client = _endpoints_client(tmp_path, tester)
    url = "/api/providers/compatible"
    refused = client.post(url, json=_endpoint_body(base_url=base_url))
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "endpoint_cloud_consent_required"
    assert client.get(url).json() == []
    assert not (tmp_path / "voz" / SECRETS_FILENAME).exists()
    assert not (tmp_path / "voz" / ENDPOINTS_FILENAME).exists()
    assert tester.keys == []

    accepted = client.post(
        url, json=_endpoint_body(base_url=base_url, cloud_consent=True)
    )
    assert accepted.status_code == 201
    endpoint = accepted.json()
    assert endpoint["cloud"] is True and endpoint["cloud_consent"] is True
    assert tester.keys == []
    tested = client.post(f"{url}/{endpoint['id']}/test")
    assert tested.status_code == 200 and tester.keys == [KEY]
    for response in (refused, accepted, tested, client.get(url)):
        assert KEY not in response.text
    assert KEY not in caplog.text


@pytest.mark.parametrize("initial_cloud", [False, True])
def test_refused_url_edit_preserves_endpoint_and_key(
    tmp_path: Path, initial_cloud: bool
) -> None:
    tester = _Tester()
    client = _endpoints_client(tmp_path, tester)
    base_url = (
        "https://first.example.com/v1" if initial_cloud else "http://localhost:8000/v1"
    )
    created = client.post(
        "/api/providers/compatible",
        json=_endpoint_body(base_url=base_url, cloud_consent=initial_cloud),
    )
    assert created.status_code == 201
    endpoint = created.json()
    files = [tmp_path / "voz" / name for name in (ENDPOINTS_FILENAME, SECRETS_FILENAME)]
    before = [file.read_bytes() for file in files]
    url = f"/api/providers/compatible/{endpoint['id']}"
    refused = client.put(
        url,
        json=_endpoint_body(
            base_url="https://second.example.com/v1", key="replacement-secret"
        ),
    )
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "endpoint_cloud_consent_required"
    assert [file.read_bytes() for file in files] == before
    assert client.get("/api/providers/compatible").json() == [endpoint]
    assert tester.keys == []
    assert client.post(url + "/test").status_code == 200
    assert tester.keys == [KEY]


def test_compatible_files_stay_0600_across_update_and_delete(tmp_path: Path) -> None:
    client = _endpoints_client(tmp_path)
    url = "/api/providers/compatible"
    first = client.post(url, json=_endpoint_body(cloud_consent=True))
    assert first.status_code == 201
    assert first.json()["cloud"] is False
    assert first.json()["cloud_consent"] is False
    second = client.post(url, json=_endpoint_body(name="Second", key="second-secret"))
    assert second.status_code == 201
    files = [tmp_path / "voz" / name for name in (ENDPOINTS_FILENAME, SECRETS_FILENAME)]
    assert all(stat.S_IMODE(file.stat().st_mode) == 0o600 for file in files)

    first_url = f"{url}/{first.json()['id']}"
    updated = client.put(first_url, json=_endpoint_body(key="replacement-secret"))
    assert updated.status_code == 200 and updated.json()["key_configured"] is True
    assert all(stat.S_IMODE(file.stat().st_mode) == 0o600 for file in files)
    cleared = client.put(first_url, json=_endpoint_body(key=None, clear_key=True))
    assert cleared.status_code == 200 and cleared.json()["key_configured"] is False
    assert "replacement-secret" not in files[1].read_text(encoding="utf-8")

    deleted = client.delete(
        f"{url}/{second.json()['id']}",
        headers={"X-VOZ-Action": "delete-compatible-endpoint"},
    )
    assert deleted.status_code == 204
    assert not files[1].exists()
    assert stat.S_IMODE(files[0].stat().st_mode) == 0o600
    assert "second-secret" not in files[0].read_text(encoding="utf-8")


def test_insecure_compatible_secrets_fail_without_echo_or_mutation(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    tester = _Tester()
    client = _endpoints_client(tmp_path, tester)
    created = client.post("/api/providers/compatible", json=_endpoint_body())
    assert created.status_code == 201
    url = f"/api/providers/compatible/{created.json()['id']}"
    secrets_file = tmp_path / "voz" / SECRETS_FILENAME
    secrets_file.chmod(0o644)
    before = secrets_file.read_bytes()

    listing = client.get("/api/providers/compatible")
    assert listing.status_code == 200 and listing.json()[0]["key_configured"] is False
    responses = (
        client.post(url + "/test"),
        client.put(url, json=_endpoint_body(key="replacement-secret")),
        client.delete(url, headers={"X-VOZ-Action": "delete-compatible-endpoint"}),
    )
    for response in responses:
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "secrets_file_insecure"
        assert KEY not in response.text and str(tmp_path) not in response.text
    assert secrets_file.read_bytes() == before
    assert tester.keys == []
    assert KEY not in caplog.text and "replacement-secret" not in caplog.text


def test_malformed_url_with_consent_returns_safe_validation_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    client = _endpoints_client(tmp_path)
    response = client.post(
        "/api/providers/compatible",
        json=_endpoint_body(base_url="http://[", cloud_consent=True),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "endpoint_invalid"
    assert KEY not in response.text and KEY not in caplog.text
    assert not (tmp_path / "voz" / SECRETS_FILENAME).exists()


# --- the key belongs to the origin it was saved for -------------------------------


def _saved_key_text(tmp_path: Path) -> str:
    file = tmp_path / "voz" / SECRETS_FILENAME
    return file.read_text(encoding="utf-8") if file.exists() else ""


def test_moving_to_another_host_without_a_new_key_deletes_the_saved_key(
    tmp_path: Path,
) -> None:
    tester = _Tester()
    client = _endpoints_client(tmp_path, tester)
    created = client.post(
        "/api/providers/compatible",
        json=_endpoint_body(base_url="https://a.example.com/v1", cloud_consent=True),
    ).json()
    url = f"/api/providers/compatible/{created['id']}"
    assert created["key_configured"] is True and KEY in _saved_key_text(tmp_path)

    moved = client.put(
        url,
        json=_endpoint_body(
            base_url="https://b.example.com/v1", key=None, cloud_consent=True
        ),
    )

    assert moved.status_code == 200
    assert moved.json()["key_configured"] is False
    assert KEY not in _saved_key_text(tmp_path)
    assert client.post(url + "/test").status_code == 200
    assert tester.keys == [None]  # nothing authorises the new host


@pytest.mark.parametrize(
    ("old", "new", "kept"),
    [
        ("https://a.example.com/v1", "https://a.example.com/other", True),
        ("https://a.example.com/v1", "https://A.Example.com:443/v1/", True),
        ("https://a.example.com/v1", "https://a.example.com:8443/v1", False),
        ("https://a.example.com/v1", "https://sub.a.example.com/v1", False),
        ("http://127.0.0.1:8000/v1", "https://127.0.0.1:8000/v1", False),
        ("http://127.0.0.1:8000/v1", "http://127.0.0.1:8001/v1", False),
        ("http://127.0.0.1:8000/v1", "http://127.0.0.1:8000/v2", True),
    ],
)
def test_only_an_origin_change_drops_the_key(
    tmp_path: Path, old: str, new: str, kept: bool
) -> None:
    client = _endpoints_client(tmp_path)
    created = client.post(
        "/api/providers/compatible",
        json=_endpoint_body(base_url=old, cloud_consent=True),
    ).json()
    moved = client.put(
        f"/api/providers/compatible/{created['id']}",
        json=_endpoint_body(base_url=new, key=None, cloud_consent=True),
    )
    assert moved.status_code == 200
    assert moved.json()["key_configured"] is kept
    assert (KEY in _saved_key_text(tmp_path)) is kept


def test_a_new_key_on_a_new_origin_replaces_the_old_one(tmp_path: Path) -> None:
    client = _endpoints_client(tmp_path)
    created = client.post(
        "/api/providers/compatible",
        json=_endpoint_body(base_url="https://a.example.com/v1", cloud_consent=True),
    ).json()
    moved = client.put(
        f"/api/providers/compatible/{created['id']}",
        json=_endpoint_body(
            base_url="https://b.example.com/v1", key="fresh-key", cloud_consent=True
        ),
    )
    assert moved.json()["key_configured"] is True
    assert "fresh-key" in _saved_key_text(tmp_path)
    assert KEY not in _saved_key_text(tmp_path)


@pytest.mark.parametrize(
    "base_url",
    [
        "http://192.168.1.5/v1",
        "http://example.com/v1",
        "http://localhost.example.com/v1",
        "http://0.0.0.0:8000/v1",
    ],
)
def test_plain_http_is_refused_for_every_non_loopback_host(
    tmp_path: Path, base_url: str
) -> None:
    client = _endpoints_client(tmp_path)
    url = "/api/providers/compatible"
    refused = client.post(
        url, json=_endpoint_body(base_url=base_url, cloud_consent=True)
    )
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "endpoint_invalid"
    assert "https://" in refused.json()["detail"]["message"]
    assert client.get(url).json() == []
    assert KEY not in _saved_key_text(tmp_path)


@pytest.mark.parametrize(
    "base_url",
    ["http://127.0.0.1:8080/v1", "http://localhost/v1", "http://[::1]/v1"],
)
def test_plain_http_is_allowed_for_loopback(tmp_path: Path, base_url: str) -> None:
    created = _endpoints_client(tmp_path).post(
        "/api/providers/compatible", json=_endpoint_body(base_url=base_url)
    )
    assert created.status_code == 201 and created.json()["cloud"] is False


def test_https_remote_is_accepted_with_consent(tmp_path: Path) -> None:
    created = _endpoints_client(tmp_path).post(
        "/api/providers/compatible",
        json=_endpoint_body(
            base_url="https://remote.example.com/v1", cloud_consent=True
        ),
    )
    assert created.status_code == 201 and created.json()["cloud"] is True
