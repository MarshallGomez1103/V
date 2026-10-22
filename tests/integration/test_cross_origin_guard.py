"""A page on another origin cannot reach state-changing routes (no CORS, no token)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

import httpx
import pytest
from fastapi.testclient import TestClient

from voz.bootstrap import create_app

LOCAL = "http://127.0.0.1"


@pytest.fixture
def client() -> Iterator[httpx.Client]:
    with TestClient(create_app(), base_url=LOCAL) as test_client:
        yield cast(httpx.Client, test_client)


def _names(client: httpx.Client) -> list[str]:
    return [
        project["name"] for project in client.get("/api/projects").json()["projects"]
    ]


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.example"},
        {"Origin": "null"},
        {"Origin": "http://127.0.0.1:9"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
    ],
)
def test_cross_origin_post_is_refused_without_effect(
    client: httpx.Client, headers: dict[str, str]
) -> None:
    response = client.post("/api/projects", json={"name": "Evil"}, headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "origin_not_allowed"
    assert _names(client) == []


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": LOCAL},
        {"Sec-Fetch-Site": "same-origin"},
        {"Sec-Fetch-Site": "none"},
    ],
)
def test_local_and_non_browser_posts_still_work(
    client: httpx.Client, headers: dict[str, str]
) -> None:
    response = client.post("/api/projects", json={"name": "Mine"}, headers=headers)

    assert response.status_code == 201
    assert _names(client) == ["Mine"]


def test_reads_are_not_blocked_by_the_origin_rule(client: httpx.Client) -> None:
    assert client.get(
        "/api/health", headers={"Origin": "https://evil.example"}
    ).is_success


def test_body_less_cross_origin_post_never_reaches_the_route(
    client: httpx.Client,
) -> None:
    path = "/api/model-tasks/missing/cancel"

    assert client.post(path).status_code == 404
    refused = client.post(path, headers={"Origin": "https://evil.example"})
    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "origin_not_allowed"
