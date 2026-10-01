"""Glossary and quality-profile HTTP contracts through ASGI over real SQLite."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from sqlalchemy import Engine
from starlette.types import Message

from voz.application.project_glossary import ProjectGlossary
from voz.application.projects import CreateProject, ListProjects
from voz.domain.entities.project import Project
from voz.infrastructure.persistence.database import create_sqlite_engine
from voz.infrastructure.persistence.project_glossaries import (
    SqliteProjectGlossaryRepository,
)
from voz.infrastructure.persistence.repositories import SqliteProjectRepository
from voz.infrastructure.persistence.schema import metadata
from voz.interfaces.api.projects import create_projects_router
from voz.interfaces.api.quality_profiles import create_quality_profiles_router


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    created = create_sqlite_engine(tmp_path / "voz.sqlite3")
    metadata.create_all(created)
    yield created
    created.dispose()


@pytest.fixture
def project(engine: Engine) -> Project:
    created = Project("Clase")
    SqliteProjectRepository(engine).add(created)
    return created


@pytest.fixture
def app(engine: Engine) -> FastAPI:
    projects = SqliteProjectRepository(engine)
    application = FastAPI()
    application.include_router(
        create_projects_router(
            CreateProject(projects),
            ListProjects(projects),
            ProjectGlossary(
                projects,
                SqliteProjectGlossaryRepository(engine),
                providers=("faster-whisper", "cloud-x"),
            ),
        )
    )
    application.include_router(create_quality_profiles_router())
    return application


def call(
    app: FastAPI, method: str, path: str, body: object = None, query: str = ""
) -> tuple[int, dict[str, object]]:
    payload = b"" if body is None else json.dumps(body).encode()
    messages: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(payload)).encode()),
        ],
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 1234),
        "root_path": "",
    }
    asyncio.run(app(scope, receive, send))  # type: ignore[arg-type]
    raw = b"".join(cast(bytes, m.get("body", b"")) for m in messages)
    return int(cast(int, messages[0]["status"])), json.loads(raw)


def test_empty_glossary_reports_limits_and_supported_providers(
    app: FastAPI, project: Project
) -> None:
    status, body = call(app, "GET", f"/api/projects/{project.id}/glossary")

    assert status == 200
    assert body == {
        "terms": [],
        "max_terms": 50,
        "max_term_length": 50,
        "applies_to": ["faster-whisper", "cloud-x"],
    }


def test_put_normalizes_persists_and_get_returns_it(
    app: FastAPI, project: Project, engine: Engine
) -> None:
    path = f"/api/projects/{project.id}/glossary"

    status, body = call(
        app, "PUT", path, {"terms": [" Mitocondria ", "", "VOZ", "VOZ"]}
    )

    assert status == 200 and body["terms"] == ["Mitocondria", "VOZ"]
    assert SqliteProjectGlossaryRepository(engine).get(project.id) == (
        "Mitocondria",
        "VOZ",
    )
    assert call(app, "GET", path)[1]["terms"] == ["Mitocondria", "VOZ"]
    assert call(app, "PUT", path, {"terms": []})[1]["terms"] == []


@pytest.mark.parametrize(
    "terms", [["x" * 51], ["bad\nterm"], [f"t{i}" for i in range(51)]]
)
def test_invalid_terms_get_a_stable_422_and_keep_the_old_glossary(
    app: FastAPI, project: Project, terms: list[str]
) -> None:
    path = f"/api/projects/{project.id}/glossary"
    call(app, "PUT", path, {"terms": ["keep"]})

    status, body = call(app, "PUT", path, {"terms": terms})

    assert status == 422
    assert cast(dict[str, object], body["detail"])["code"] == "glossary_invalid"
    assert call(app, "GET", path)[1]["terms"] == ["keep"]


def test_unknown_project_is_a_typed_404(app: FastAPI) -> None:
    path = "/api/projects/00000000-0000-4000-8000-000000000000/glossary"

    for method, body in (("GET", None), ("PUT", {"terms": ["a"]})):
        status, payload = call(app, method, path, body)
        assert status == 404
        assert cast(dict[str, object], payload["detail"])["code"] == "project_not_found"


def test_quality_profiles_lists_parameters_and_a_measured_recommendation(
    app: FastAPI,
) -> None:
    status, body = call(app, "GET", "/api/quality-profiles", query="language=es-CO")

    assert status == 200
    assert body["default"] == "default"
    profiles = cast(list[dict[str, object]], body["profiles"])
    assert [p["name"] for p in profiles] == ["default", "academic"]
    academic = cast(dict[str, object], profiles[1]["parameters"])
    assert academic["condition_on_previous_text"] is False
    assert academic["vad"] is not None
    recommendation = cast(dict[str, object], body["recommendation"])
    assert recommendation["measured"] is True
    assert recommendation["profile"] == "default"
    assert recommendation["synthetic"] is True


def test_quality_profiles_say_sin_medicion_instead_of_inventing(
    app: FastAPI,
) -> None:
    for query in ("language=fr", ""):
        _, body = call(app, "GET", "/api/quality-profiles", query=query)
        recommendation = cast(dict[str, object], body["recommendation"])

        assert recommendation["measured"] is False
        assert recommendation["profile"] is None
        assert "sin medición" in cast(str, recommendation["evidence"])
