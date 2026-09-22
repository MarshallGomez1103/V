"""Projects HTTP contract exercised through ASGI over real SQLite repositories."""

import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy import Engine
from starlette.types import Message

from voz.application.projects import CreateProject, ListProjects
from voz.domain.entities.project import Project
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.repositories import SqliteProjectRepository
from voz.infrastructure.persistence.schema import metadata
from voz.interfaces.api.projects import create_projects_router

BASE_TIME = datetime(2026, 9, 21, 8, tzinfo=UTC)


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_sqlite_engine(tmp_path / "voz.sqlite3")
    metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def repository(engine: Engine) -> SqliteProjectRepository:
    return SqliteProjectRepository(engine)


@pytest.fixture
def app(repository: SqliteProjectRepository) -> FastAPI:
    application = FastAPI()
    application.include_router(
        create_projects_router(CreateProject(repository), ListProjects(repository))
    )
    return application


async def request(
    app: FastAPI,
    method: str,
    path: str,
    body: bytes = b"",
) -> tuple[int, object]:
    messages: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    headers: list[tuple[bytes, bytes]] = [(b"content-length", str(len(body)).encode())]
    if body:
        headers.append((b"content-type", b"application/json"))
    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": headers,
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1234),
            "root_path": "",
        },
        receive,
        send,
    )
    payload = b"".join(message.get("body", b"") for message in messages)
    return int(messages[0]["status"]), json.loads(payload)


def call(
    app: FastAPI, method: str, path: str, body: object = None
) -> tuple[int, object]:
    encoded = b"" if body is None else json.dumps(body).encode()
    return asyncio.run(request(app, method, path, encoded))


def test_create_then_list_round_trips_through_sqlite(
    app: FastAPI, repository: SqliteProjectRepository
) -> None:
    status, created = call(app, "POST", "/api/projects", {"name": "  Seminario  "})

    assert status == 201
    created_body = cast(dict[str, object], created)
    assert set(created_body) == {"id", "name", "created_at"}
    assert created_body["name"] == "Seminario"
    created_at = datetime.fromisoformat(cast(str, created_body["created_at"]))
    assert created_at.tzinfo is not None
    stored = repository.get(UUID(cast(str, created_body["id"])))
    assert stored is not None and stored.name == "Seminario"

    status, listed = call(app, "GET", "/api/projects")

    assert status == 200
    assert listed == {"projects": [created_body]}


def test_list_orders_newest_first(
    app: FastAPI, repository: SqliteProjectRepository
) -> None:
    older = Project("Older", created_at=BASE_TIME - timedelta(days=1))
    repository.add(older)

    status, _ = call(app, "POST", "/api/projects", {"name": "Newer"})
    assert status == 201
    _, listed = call(app, "GET", "/api/projects")

    projects = cast(
        list[dict[str, object]], cast(dict[str, object], listed)["projects"]
    )
    assert [project["name"] for project in projects] == ["Newer", "Older"]
    assert projects[1]["id"] == str(older.id)


def test_list_is_empty_on_fresh_database(app: FastAPI) -> None:
    assert call(app, "GET", "/api/projects") == (200, {"projects": []})


@pytest.mark.parametrize("name", ["", "   ", "x" * 201, "tab\there"])
def test_invalid_name_returns_typed_422_and_persists_nothing(
    app: FastAPI, repository: SqliteProjectRepository, name: str
) -> None:
    status, body = call(app, "POST", "/api/projects", {"name": name})

    assert status == 422
    detail = cast(dict[str, object], cast(dict[str, object], body)["detail"])
    assert detail["code"] == "project_name_invalid"
    assert isinstance(detail["message"], str) and detail["message"]
    assert repository.list_all() == ()


@pytest.mark.parametrize(
    "raw",
    [b"{not json", b'{"name": 5}', b'{"title": "x"}', b"[]", b""],
)
def test_malformed_body_is_a_client_error_not_500(app: FastAPI, raw: bytes) -> None:
    status, body = asyncio.run(request(app, "POST", "/api/projects", raw))

    assert status == 422
    assert "detail" in cast(dict[str, object], body)
