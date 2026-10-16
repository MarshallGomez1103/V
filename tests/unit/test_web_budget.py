"""Bundle budgets exercised through the standalone command."""

from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/check-web-budget.py"


def _run(static: Path, *options: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--static-dir", str(static), *options],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    assets = tmp_path / "assets"
    assets.mkdir()
    (tmp_path / "index.html").write_text(
        '<script type="module" src="/assets/index-test.js"></script>'
        '<link rel="stylesheet" href="/assets/index-test.css">'
        '<link rel="modulepreload" href="/assets/shared.js">',
        encoding="utf-8",
    )
    (assets / "index-test.js").write_text(
        'import("./ModelManager-test.js");', encoding="utf-8"
    )
    (assets / "index-test.css").write_text("body{color:black}", encoding="utf-8")
    (assets / "ModelManager-test.js").write_text("export{};", encoding="utf-8")
    (assets / "shared.js").write_text("export{};", encoding="utf-8")
    return tmp_path


def test_small_bundle_is_deterministic_and_has_text_output(bundle: Path) -> None:
    first = _run(bundle, "--json")
    assert first.returncode == 0, first.stdout
    assert first.stdout == _run(bundle, "--json").stdout
    payload = json.loads(first.stdout)
    assert payload["status"] == "ok"
    assert {item["name"] for item in payload["assets"]} == {
        "entry_js",
        "entry_css",
        "model_manager",
    }
    text = _run(bundle)
    assert text.returncode == 0
    assert "entry_js" in text.stdout and "gzip" in text.stdout
    assert str(bundle) not in text.stdout + first.stdout


@pytest.mark.parametrize(
    "asset", ["index-test.js", "index-test.css", "ModelManager-test.js"]
)
def test_raw_budget_excess_fails(bundle: Path, asset: str) -> None:
    with (bundle / "assets" / asset).open("ab") as handle:
        handle.write(b"x" * (701 * 1024))
    result = _run(bundle, "--json")
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "budget_exceeded"


@pytest.mark.parametrize(
    ("asset", "limit"),
    [
        ("index-test.js", 400 * 1024),
        ("index-test.css", 700 * 1024),
        ("ModelManager-test.js", 32 * 1024),
    ],
)
def test_raw_budget_limit_is_inclusive(bundle: Path, asset: str, limit: int) -> None:
    path = bundle / "assets" / asset
    original = path.read_bytes()
    path.write_bytes(original + b" " * (limit - len(original)))
    assert _run(bundle, "--json").returncode == 0


def test_gzip_budget_can_fail_below_raw_limit(bundle: Path) -> None:
    (bundle / "assets/ModelManager-test.js").write_bytes(
        random.Random(0).randbytes(20 * 1024)
    )
    result = _run(bundle, "--json")
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    measured = next(
        item for item in payload["assets"] if item["name"] == "model_manager"
    )
    assert measured["raw_bytes"] < measured["raw_limit_bytes"]
    assert measured["gzip_bytes"] > measured["gzip_limit_bytes"]


@pytest.mark.parametrize(
    "asset", ["index-test.js", "index-test.css", "ModelManager-test.js", "shared.js"]
)
def test_missing_referenced_asset_is_invalid(bundle: Path, asset: str) -> None:
    (bundle / "assets" / asset).unlink()
    result = _run(bundle, "--json")
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "invalid"
    assert str(bundle) not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "reference",
    [
        "../outside.js",
        "/assets/../../outside.js",
        "/assets/%2e%2e/outside.js",
        "https://example.test/app.js",
        "//example.test/app.js",
        r"assets\outside.js",
    ],
)
def test_unsafe_reference_is_invalid(bundle: Path, reference: str) -> None:
    with (bundle / "index.html").open("a", encoding="utf-8") as handle:
        handle.write(f'<script src="{reference}"></script>')
    result = _run(bundle, "--json")
    assert result.returncode == 2
    assert json.loads(result.stdout)["code"] == "web_budget_invalid"
    assert reference not in result.stdout + result.stderr


def test_symlink_cannot_escape_static(bundle: Path, tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.js"
    outside.write_text("export{};", encoding="utf-8")
    shared = bundle / "assets/shared.js"
    shared.unlink()
    shared.symlink_to(outside)
    result = _run(bundle, "--json")
    assert result.returncode == 2
    assert str(outside) not in result.stdout + result.stderr


def test_real_shipped_bundle_meets_budgets() -> None:
    result = _run(REPO / "src/voz/static", "--json")
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert len(payload["assets"]) == 3
    assert all(item["within_budget"] for item in payload["assets"])
