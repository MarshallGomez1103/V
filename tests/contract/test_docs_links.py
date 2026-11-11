"""Relative links and anchors in the repository's Markdown resolve to files and
headings that exist."""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import unquote

import pytest

REPO = Path(__file__).parents[2]
# Not documentation we author: tooling, dependencies, build output, the
# generated bundle and the audit reports (historical snapshots).
SKIPPED_NAMES = {"node_modules", "__pycache__", "dist", "build", "coverage"}
SKIPPED_PATHS = ("docs/audits", "src/voz/static")

FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
CODE_SPAN = re.compile(r"(`+).+?\1")
# [text](dest "title") and ![alt](dest); dest is <...> or has no spaces and
# balanced parentheses.
INLINE_LINK = re.compile(
    r"\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*(<[^>]+>|(?:[^\s()]|\([^\s()]*\))+)"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)"
)
REFERENCE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]+>|\S+)")
HEADING = re.compile(r"^ {0,3}#{1,6}[ \t]+(.+?)[ \t]*$")
HTML_ANCHOR = re.compile(r"""\b(?:id|name)=["']([^"']+)["']""")
SCHEME = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//)")


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lowercase, spaces to hyphens, and only
    letters, digits, ``-`` and ``_`` kept."""
    text = re.sub(r"[ \t]+#+$", "", heading)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text).replace("`", "").replace("*", "")
    kept = "".join(c for c in text.strip().lower() if c.isalnum() or c in " -_")
    return kept.replace(" ", "-")


def _prose(text: str) -> list[tuple[int, str]]:
    """``(line number, line)`` outside fenced code."""
    lines: list[tuple[int, str]] = []
    fence = ""
    for number, line in enumerate(text.splitlines(), 1):
        marker = FENCE.match(line)
        if fence:
            if (
                marker
                and marker.group(1)[0] == fence[0]
                and len(marker.group(1)) >= len(fence)
            ):
                fence = ""
            continue
        if marker:
            fence = marker.group(1)
            continue
        lines.append((number, line))
    return lines


def anchors(text: str) -> set[str]:
    found: set[str] = set()
    seen: dict[str, int] = {}
    for _, line in _prose(text):
        heading = HEADING.match(line)
        if heading:
            base = slug(heading.group(1))
            count = seen.get(base, 0)
            seen[base] = count + 1
            found.add(base if count == 0 else f"{base}-{count}")
        found.update(HTML_ANCHOR.findall(line))
    return found


def links(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for number, raw in _prose(text):
        line = CODE_SPAN.sub(" ", raw)
        destinations = [m.group(1) for m in INLINE_LINK.finditer(line)]
        reference = REFERENCE.match(line)
        if reference:
            destinations.append(reference.group(1))
        found.extend((number, d.strip("<>")) for d in destinations)
    return found


def markdown_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for folder, names, filenames in os.walk(root):
        here = Path(folder)
        names[:] = sorted(
            name
            for name in names
            if name not in SKIPPED_NAMES
            and (name == ".github" or not name.startswith("."))
            and (here / name).relative_to(root).as_posix() not in SKIPPED_PATHS
        )
        files.extend(here / name for name in sorted(filenames) if name.endswith(".md"))
    return files


def broken_links(root: Path) -> list[str]:
    """Every relative link or anchor that does not resolve, as
    ``file:line: destination (reason)`` messages."""
    problems: list[str] = []
    cache: dict[Path, set[str]] = {}

    def headings(path: Path) -> set[str]:
        if path not in cache:
            cache[path] = anchors(path.read_text(encoding="utf-8"))
        return cache[path]

    for source in markdown_files(root):
        shown = source.relative_to(root).as_posix()
        for number, destination in links(source.read_text(encoding="utf-8")):
            if not destination or SCHEME.match(destination):
                continue
            path, _, fragment = destination.partition("#")
            path = unquote(path.split("?", 1)[0])
            fragment = unquote(fragment).lower()
            where = f"{shown}:{number}: {destination}"
            if not path:
                target = source
            else:
                base = root if path.startswith("/") else source.parent
                target = base / path.lstrip("/")
                if not target.exists():
                    problems.append(f"{where} (no such file)")
                    continue
            if (
                fragment
                and target.suffix == ".md"
                and target.is_file()
                and fragment not in {a.lower() for a in headings(target)}
            ):
                problems.append(f"{where} (no such heading)")
    return problems


def test_repository_links_and_anchors_resolve() -> None:
    assert broken_links(REPO) == []


def _tree(root: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def test_a_broken_file_link_names_file_line_and_destination(tmp_path: Path) -> None:
    _tree(tmp_path, {"README.md": "intro\n\nSee [guide](docs/guide.md).\n"})
    assert broken_links(tmp_path) == ["README.md:3: docs/guide.md (no such file)"]


def test_a_broken_anchor_is_reported_in_the_same_and_other_files(
    tmp_path: Path,
) -> None:
    _tree(
        tmp_path,
        {
            "README.md": "# Title\n\n[a](#title) [b](#nope) [c](docs/g.md#missing)\n",
            "docs/g.md": "## Real heading\n",
        },
    )
    assert broken_links(tmp_path) == [
        "README.md:3: #nope (no such heading)",
        "README.md:3: docs/g.md#missing (no such heading)",
    ]


def test_valid_links_pass(tmp_path: Path) -> None:
    _tree(
        tmp_path,
        {
            "README.md": (
                "# Top\n\n[g](docs/g.md#a-b--c) [dir](docs/) [up](../x)\n"
                "![img](docs/pic.png) [dup](docs/g.md#same-1) [abs](/docs/g.md)\n"
                '[t](docs/g.md "title") [h](docs/g.md#a-b--c)\n'
                "[e](docs/g.md#caf%C3%A9)\n"
                "[ref]: docs/g.md#html-id\n"
            ),
            "docs/g.md": (
                '## A, b & C\n\n## Same\n\n## Same\n\n## Café\n\n<a id="html-id"></a>\n'
            ),
            "docs/pic.png": "",
        },
    )
    # `../x` leaves the repo copy on purpose: only the root level is checked.
    assert broken_links(tmp_path) == ["README.md:3: ../x (no such file)"]


def test_external_links_code_and_remote_images_are_ignored(tmp_path: Path) -> None:
    _tree(
        tmp_path,
        {
            "README.md": (
                "[w](https://example.org/x) [m](mailto:a@b.c) ![i](https://e.org/i.png)\n"
                "`[c](missing.md)`\n\n```\n[d](missing.md)\n```\n\n~~~md\n[e](gone.md)\n~~~\n"
                "[ok](#ok)\n\n# Ok\n"
            )
        },
    )
    assert broken_links(tmp_path) == []


def test_skipped_folders_are_not_scanned(tmp_path: Path) -> None:
    broken = "[x](missing.md)\n"
    _tree(
        tmp_path,
        {
            "docs/audits/a.md": broken,
            "node_modules/p/README.md": broken,
            ".venv/lib/README.md": broken,
            "src/voz/static/a.md": broken,
            "docs/real.md": broken,
        },
    )
    assert broken_links(tmp_path) == ["docs/real.md:1: missing.md (no such file)"]


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("Hello World", "hello-world"),
        ("`code` and *emphasis*", "code-and-emphasis"),
        ("A, b & C", "a-b--c"),
        ("Section 18 — Range", "section-18--range"),
        ("[Link](x.md) text", "link-text"),
        ("snake_case-name", "snake_case-name"),
        ("Closed ##", "closed"),
    ],
)
def test_slug_follows_the_github_rule(heading: str, expected: str) -> None:
    assert slug(heading) == expected
