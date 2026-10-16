"""The composed application protects static, API and denied responses."""

from typing import cast

import httpx
from fastapi.testclient import TestClient

from voz.bootstrap import create_app


def test_default_headers_cover_api_static_auth_and_host_denials() -> None:
    token = "h" * 43
    with TestClient(create_app(auth_token=token)) as raw:
        client = cast(httpx.Client, raw)
        responses = [
            client.get("/api/health"),
            client.get("/api/health", headers={"Host": "evil.example"}),
            client.get("/", headers={"Authorization": "Bearer " + token}),
            client.get("/api/health", headers={"Authorization": "Bearer " + token}),
        ]
        assert [response.status_code for response in responses] == [401, 400, 200, 200]
        for response in responses:
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["x-frame-options"] == "DENY"
            assert "script-src 'self'" in response.headers["content-security-policy"]
            assert response.headers["referrer-policy"] == "no-referrer"
            assert "strict-transport-security" not in response.headers
