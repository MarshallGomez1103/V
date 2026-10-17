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
POSIX = (
    "start-v-linux.sh",
    "Start-V-macOS.command",
    "Iniciar-Linux.sh",
    "Iniciar-Mac.command",
)


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


def test_windows_launcher_and_legacy_alias_keep_quoted_paths_and_arguments() -> None:
    launcher = (ROOT / "Start-V-Windows.bat").read_text()
    alias = (ROOT / "Iniciar-Windows.bat").read_text()
    assert 'cd /d "%~dp0"' in launcher
    assert 'set "PATH=%USERPROFILE%\\.local\\bin;%PATH%"' in launcher
    assert "uv run --extra asr-local --extra diarization voz %*" in launcher
    assert 'call "%~dp0Start-V-Windows.bat" %*' in alias
    assert "exit /b %errorlevel%" in alias
