"""Exercise POSIX launchers with a local uv stub; Windows is a static check."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
POSIX = ("start-v-linux.sh", "Start-V-macOS.command")


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell execution")
@pytest.mark.parametrize("launcher", POSIX)
def test_posix_launcher_forwards_arguments_from_a_path_with_spaces(
    tmp_path: Path, launcher: str
) -> None:
    checkout = tmp_path / "V portable with spaces"
    checkout.mkdir()
    for name in POSIX:
        shutil.copyfile(ROOT / name, checkout / name)
    home = tmp_path / "home"
    uv = home / ".local/bin/uv"
    uv.parent.mkdir(parents=True)
    uv.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        'Path(os.environ["UV_RECORD"]).write_text(json.dumps({'
        '"args": sys.argv[1:], "cwd": os.getcwd(), "home": os.environ["HOME"]}))\n'
    )
    uv.chmod(0o755)
    record = tmp_path / "uv.json"
    result = subprocess.run(
        ["sh", str(checkout / launcher), "--no-browser", "--host", "a b", "literal;$x"],
        env={
            **os.environ,
            **{
                key: str(home / key)
                for key in (
                    "XDG_CONFIG_HOME",
                    "XDG_DATA_HOME",
                    "XDG_CACHE_HOME",
                    "XDG_STATE_HOME",
                    "XDG_RUNTIME_DIR",
                )
            },
            "HOME": str(home),
            "UV_RECORD": str(record),
        },
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(record.read_text()) == {
        "args": [
            "run",
            "--extra",
            "asr-local",
            "--extra",
            "diarization",
            "voz",
            "--no-browser",
            "--host",
            "a b",
            "literal;$x",
        ],
        "cwd": str(checkout),
        "home": str(home),
    }


@pytest.mark.skipif(os.name == "nt", reason="POSIX shell execution")
def test_posix_launcher_explains_a_failed_uv_install_without_waiting(
    tmp_path: Path,
) -> None:
    fake = tmp_path / "fake-bin"
    fake.mkdir()
    for tool in ("curl", "wget"):
        (fake / tool).write_text("#!/bin/sh\nexit 6\n")
        (fake / tool).chmod(0o755)
    path = f"{fake}{os.pathsep}/usr/bin{os.pathsep}/bin"
    if shutil.which("uv", path=path):
        pytest.skip("uv is installed system-wide")
    result = subprocess.run(
        ["sh", str(ROOT / "start-v-linux.sh")],
        env={"HOME": str(tmp_path / "home"), "PATH": path},
        stdin=subprocess.DEVNULL,  # not a terminal: it must not wait for Enter
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 1
    assert "Could not install uv" in result.stdout


def test_windows_launcher_keeps_quoted_paths_and_arguments() -> None:
    launcher = (ROOT / "Start-V-Windows.bat").read_text()
    assert 'cd /d "%~dp0"' in launcher
    assert 'set "PATH=%USERPROFILE%\\.local\\bin;%PATH%"' in launcher
    assert "uv run --extra asr-local --extra diarization voz %*" in launcher


def test_windows_launcher_reports_failures_and_can_skip_the_pause() -> None:
    launcher = (ROOT / "Start-V-Windows.bat").read_text()
    # A failed install must be caught (uv still missing) and must exit non-zero.
    assert launcher.count("where uv") == 2
    assert 'set "UV_INSTALL_DIR=%USERPROFILE%\\.local\\bin"' in launcher
    assert "if not defined VOZ_NO_PAUSE pause" in launcher
    assert launcher.rstrip().endswith("exit /b 1")


def test_legacy_iniciar_wrappers_are_gone() -> None:
    assert not list(ROOT.glob("Iniciar-*"))
