"""Check the shipped web assets without building or downloading anything."""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections.abc import Sequence
from html.parser import HTMLParser
from pathlib import Path
from typing import NoReturn, TypedDict

DEFAULT_STATIC = Path(__file__).resolve().parents[1] / "src/voz/static"


class InvalidBundle(Exception):
    """Missing, ambiguous or unsafe bundle input; never include host paths."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise InvalidBundle


class _Index(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []
        self.modules: list[str] = []
        self.styles: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "base":
            raise InvalidBundle
        values = dict(attrs)
        if len(values) != len(attrs):
            raise InvalidBundle
        for name in ("src", "href", "poster"):
            if name in values:
                value = values[name]
                if not value:
                    raise InvalidBundle
                self.references.append(value)
        if tag == "script" and values.get("type") == "module":
            self.modules.append(values.get("src") or "")
        if tag == "link" and "stylesheet" in (values.get("rel") or "").split():
            self.styles.append(values.get("href") or "")


class Measurement(TypedDict):
    name: str
    file: str
    raw_bytes: int
    gzip_bytes: int
    raw_limit_bytes: int
    gzip_limit_bytes: int
    within_budget: bool


def _asset(root: Path, reference: str) -> Path:
    if (
        re.fullmatch(r"/?[A-Za-z0-9_./-]+", reference) is None
        or reference.startswith("//")
        or ".." in reference.split("/")
    ):
        raise InvalidBundle
    target = (root / reference.removeprefix("/")).resolve(strict=True)
    if not target.is_relative_to(root) or not target.is_file():
        raise InvalidBundle
    return target


def measure_bundle(static: Path) -> list[Measurement]:
    root = static.resolve(strict=True)
    index = _Index()
    index.feed(_asset(root, "index.html").read_text(encoding="utf-8"))
    for reference in index.references:
        _asset(root, reference)
    if len(index.modules) != 1:
        raise InvalidBundle
    entry = _asset(root, index.modules[0])
    styles = {
        _asset(root, reference)
        for reference in index.styles
        if re.fullmatch(r"index(?:-[A-Za-z0-9_-]+)?\.css", Path(reference).name)
    }
    if entry.suffix != ".js" or len(styles) != 1:
        raise InvalidBundle
    # ponytail: inspect emitted ModelManager references, not a JavaScript AST;
    # use a build manifest if the bundler changes its chunk naming contract.
    references = re.findall(
        r"""["'`]([^"'`\s]*ModelManager-[^"'`\s]*\.js)["'`]""",
        entry.read_text(encoding="utf-8"),
    )
    chunks = {
        _asset(
            root,
            (
                f"{entry.relative_to(root).parent.as_posix()}/{reference}"
                if reference.startswith("./")
                else reference
            ),
        )
        for reference in references
    }
    if len(chunks) != 1:
        raise InvalidBundle
    measurements: list[Measurement] = []
    for name, path, raw_kib, gzip_kib in (
        ("entry_js", entry, 400, 128),
        ("entry_css", next(iter(styles)), 700, 80),
        ("model_manager", next(iter(chunks)), 32, 12),
    ):
        body = path.read_bytes()
        raw_size = len(body)
        gzip_size = len(gzip.compress(body, compresslevel=9, mtime=0))
        measurements.append(
            {
                "name": name,
                "file": path.relative_to(root).as_posix(),
                "raw_bytes": raw_size,
                "gzip_bytes": gzip_size,
                "raw_limit_bytes": raw_kib * 1024,
                "gzip_limit_bytes": gzip_kib * 1024,
                "within_budget": raw_size <= raw_kib * 1024
                and gzip_size <= gzip_kib * 1024,
            }
        )
    return measurements


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = _Parser(prog="check-web-budget", description=__doc__)
    parser.add_argument("--static-dir", type=Path, default=DEFAULT_STATIC)
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON."
    )
    try:
        options = parser.parse_args(arguments)
        measurements = measure_bundle(options.static_dir)
    except (InvalidBundle, OSError, UnicodeError, ValueError, RuntimeError):
        error = {
            "status": "invalid",
            "code": "web_budget_invalid",
            "message": "The web bundle is missing, unsafe or ambiguous.",
        }
        print(
            json.dumps(error)
            if "--json" in arguments
            else f"{error['code']}: {error['message']}"
        )
        return 2
    passed = all(item["within_budget"] for item in measurements)
    status = "ok" if passed else "budget_exceeded"
    code = "web_budget_ok" if passed else "web_budget_exceeded"
    if options.json:
        print(json.dumps({"status": status, "code": code, "assets": measurements}))
    else:
        print(code)
        for item in measurements:
            print(
                f"{item['name']}: "
                f"raw {item['raw_bytes']}/{item['raw_limit_bytes']} bytes; "
                f"gzip {item['gzip_bytes']}/{item['gzip_limit_bytes']} bytes; "
                f"{'PASS' if item['within_budget'] else 'FAIL'}"
            )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
