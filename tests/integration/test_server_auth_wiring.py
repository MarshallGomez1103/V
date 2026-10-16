"""Authentication protects the default application without weakening Host checks."""

import base64
from typing import cast

import httpx
from fastapi.testclient import TestClient

from voz.bootstrap import create_app

TOKEN = "a" * 43


def test_default_application_requires_auth_for_api_assets_and_files() -> None:
    with TestClient(
        create_app(auth_token=TOKEN), base_url="http://127.0.0.1"
    ) as raw_client:
        client = cast(httpx.Client, raw_client)
        for path in (
            "/",
            "/api/health",
            "/api/models",
            "/assets/missing.js",
            "/api/media/missing/original",
        ):
            denied = client.get(path)
            assert denied.status_code == 401
            assert TOKEN not in denied.text
        assert (
            client.get(
                "/api/health", headers={"Authorization": "Bearer " + TOKEN}
            ).status_code
            == 200
        )
        basic = base64.b64encode(("v:" + TOKEN).encode()).decode()
        assert (
            client.get("/", headers={"Authorization": "Basic " + basic}).status_code
            == 200
        )
        assert (
            client.post(
                "/api/projects",
                json={"name": "Blocked"},
                headers={"Authorization": "Basic " + basic},
            ).status_code
            == 401
        )
        assert (
            client.get(
                "/api/health",
                headers={
                    "Host": "untrusted.invalid",
                    "Authorization": "Bearer " + TOKEN,
                },
            ).status_code
            == 400
        )
