"""Every route the real application serves is documented in ``docs/api``, and
every endpoint those pages name is served."""

from __future__ import annotations

import re
from pathlib import Path

from voz.bootstrap import create_app
from voz.infrastructure.paths import VozPaths

DOCS = Path(__file__).parents[2] / "docs/api"
# `METHOD /path` in code spans: the heading and table convention of the pages.
ENDPOINT = re.compile(r"`(GET|POST|PUT|PATCH|DELETE) (/(?:api|v1)/[^`\s]*)`")
PARAMETER = re.compile(r"\{[^}]*\}")


def _key(method: str, path: str) -> tuple[str, str]:
    path = PARAMETER.sub("{}", path.split("?", 1)[0])
    return method, path if path == "/" else path.rstrip("/")


def _served(tmp_path: Path) -> set[tuple[str, str]]:
    for name in ("config", "data", "cache", "state"):
        (tmp_path / name).mkdir()
    app = create_app(
        paths=VozPaths(
            tmp_path / "config",
            tmp_path / "data",
            tmp_path / "cache",
            tmp_path / "state",
        )
    )
    # The generated schema lists every mounted route; FastAPI's own /docs and
    # /openapi.json are not part of it. No route opts out of the schema.
    return {
        _key(method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }


def _documented() -> set[tuple[str, str]]:
    return {
        _key(method, path)
        for page in sorted(DOCS.glob("*.md"))
        for method, path in ENDPOINT.findall(page.read_text(encoding="utf-8"))
    }


def test_every_served_route_is_documented(tmp_path: Path) -> None:
    missing = sorted(_served(tmp_path) - _documented())
    assert not missing, f"Routes served but not documented in docs/api: {missing}"


def test_every_documented_endpoint_is_served(tmp_path: Path) -> None:
    unknown = sorted(_documented() - _served(tmp_path))
    assert not unknown, f"Endpoints documented in docs/api but not served: {unknown}"
