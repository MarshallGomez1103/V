"""V10-04: exercise Flatpak staging without installing or downloading anything."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FLATPAK = ROOT / "packaging" / "flatpak"
POSIX_ONLY = pytest.mark.skipif(
    os.name == "nt", reason="Flatpak build and executable stubs require POSIX"
)


def test_flatpak_manifest_and_metainfo_share_v_branding() -> None:
    (manifest,) = FLATPAK.glob("*.yml")
    app_id = manifest.stem
    assert app_id == "io.github.marshallgomez1103.v"
    content = manifest.read_text(encoding="utf-8")
    assert f"app-id: {app_id}\n" in content
    assert "command: v\n" in content
    for resource in ("desktop", "svg", "metainfo.xml"):
        assert f"stage/{app_id}.{resource}" in content
    metadata = ET.parse(FLATPAK / f"{app_id}.metainfo.xml").getroot()
    assert metadata.findtext("id") == app_id
    assert metadata.findtext("name") == "V"
    assert metadata.findtext("summary") == "Local Voice AI"
    assert metadata.findtext("url[@type='homepage']") == (
        "https://github.com/MarshallGomez1103/V"
    )
    assert metadata.findtext("launchable") == f"{app_id}.desktop"
    assert "V transcribes" in " ".join(metadata.itertext())


def _build(
    tmp_path: Path, *, extras: str = "", failure: str = ""
) -> tuple[subprocess.CompletedProcess[str], Path, list[list[str]]]:
    checkout = tmp_path / "checkout with spaces"
    shutil.copytree(FLATPAK, checkout / "packaging" / "flatpak")
    common = checkout / "packaging" / "common"
    common.mkdir()
    (common / "v.desktop").write_text(
        "[Desktop Entry]\nName=V\nGenericName=Local Voice AI\nExec=v\nIcon=v\n",
        encoding="utf-8",
    )
    (common / "v.svg").write_text("<svg>V fixture</svg>", encoding="utf-8")
    # Keep the old resources in the fixture so the previous build can reach
    # the observable host-install regression rather than failing on a copy.
    (common / "voz.desktop").write_text(
        "[Desktop Entry]\nName=VOZ\nExec=voz\nIcon=voz\n", encoding="utf-8"
    )
    (common / "voz.svg").write_text("<svg>old fixture</svg>", encoding="utf-8")
    wheel_directory = tmp_path / "wheel with spaces"
    wheel_directory.mkdir()
    wheel = wheel_directory / "voz_transcriber-1.2.3-py3-none-any.whl"
    wheel.write_bytes(b"fixture wheel: never installed")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    stub = binaries / "flatpak"
    stub.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "with open(os.environ['FLATPAK_CALLS'], 'a') as log:\n"
        "    log.write(json.dumps(args) + '\\n')\n"
        "assert '--install' not in args, 'unexpected host installation'\n"
        "if os.environ['FLATPAK_FAILURE'] == args[0]:\n"
        "    print('fixture Flatpak failure: ' + args[0], file=sys.stderr)\n"
        "    sys.exit(7)\n"
        "if args[0] == 'build-bundle':\n"
        "    pathlib.Path(args[2]).write_bytes(b'fixture bundle')\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    work = tmp_path / "work with spaces"
    calls = tmp_path / "calls.jsonl"
    home = tmp_path / "home"
    home.mkdir()
    environment = {
        **os.environ,
        "HOME": str(home),
        "XDG_DATA_HOME": str(home / "data"),
        "XDG_CACHE_HOME": str(home / "cache"),
        "XDG_CONFIG_HOME": str(home / "config"),
        "XDG_STATE_HOME": str(home / "state"),
        "PATH": f"{binaries}:{os.environ['PATH']}",
        "VOZ_WORK": str(work),
        "VOZ_OUT": str(tmp_path / "output with spaces"),
        "VOZ_EXTRAS": extras,
        "FLATPAK_CALLS": str(calls),
        "FLATPAK_FAILURE": failure,
    }
    result = subprocess.run(
        ["bash", str(checkout / "packaging" / "flatpak" / "build.sh"), str(wheel)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=10,
        check=False,
    )
    invocations: list[list[str]] = [
        json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()
    ]
    return result, work, invocations


@pytest.mark.parametrize("extras", ["", "asr-local"])
@POSIX_ONLY
def test_build_stages_v_and_bundles_without_installing(
    tmp_path: Path, extras: str
) -> None:
    result, work, calls = _build(tmp_path, extras=extras)
    assert result.returncode == 0, result.stdout + result.stderr
    (manifest,) = work.glob("*.yml")
    app_id = manifest.stem
    assert app_id == "io.github.marshallgomez1103.v"
    assert calls[0][:4] == ["run", "--user", "org.flatpak.Builder", "--user"]
    assert "--install" not in calls[0]
    assert f"--repo={work / 'repo'}" in calls[0]
    assert calls[0][-2:] == ["build", manifest.name]
    suffix = f"-{extras}" if extras else ""
    bundle = tmp_path / "output with spaces" / f"V-1.2.3{suffix}-x86_64.flatpak"
    assert calls[1] == ["build-bundle", str(work / "repo"), str(bundle), app_id]
    assert bundle.read_bytes() == b"fixture bundle"
    stage = work / "stage"
    desktop = (stage / f"{app_id}.desktop").read_text(encoding="utf-8")
    assert "Name=V\n" in desktop
    assert "Exec=v\n" in desktop
    assert f"Icon={app_id}\n" in desktop
    assert (stage / "voz_transcriber-1.2.3-py3-none-any.whl").read_bytes() == (
        b"fixture wheel: never installed"
    )
    icon = (stage / f"{app_id}.svg").read_text(encoding="utf-8")
    assert icon == "<svg>V fixture</svg>"
    assert (stage / f"{app_id}.metainfo.xml").is_file()
    content = manifest.read_text(encoding="utf-8")
    assert "EXTRAS_SPEC" not in content
    spec = f"[{extras}]" if extras else ""
    assert f'"$(ls stage/*.whl){spec}"' in content


@pytest.mark.parametrize("failure", ["run", "build-bundle"])
@POSIX_ONLY
def test_build_reports_flatpak_failures(tmp_path: Path, failure: str) -> None:
    result, _, calls = _build(tmp_path, failure=failure)
    assert result.returncode != 0
    assert f"fixture Flatpak failure: {failure}" in result.stderr
    assert len(calls) == (1 if failure == "run" else 2)
    assert not tuple((tmp_path / "output with spaces").glob("*.flatpak"))
