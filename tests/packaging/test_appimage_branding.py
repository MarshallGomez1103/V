"""Exercise AppImage staging and its launcher without downloads or FUSE."""

from __future__ import annotations

import configparser
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_INSTALLER_FILES = (
    "bin/pip",
    "bin/pip3",
    "bin/pip3.12",
    "lib/python3.12/site-packages/pip/_vendor/certifi/cacert.pem",
    "lib/python3.12/site-packages/pip-26.2.1.dist-info/METADATA",
    "lib/python3.12/ensurepip/_bundled/pip-25.0.1-py3-none-any.whl",
)
_RUNTIME_FILES = ("lib/python3.12/pipes.py", "lib/python3.12/os.py")


@pytest.fixture(params=["", "asr-local"])
def staged_appimage(
    tmp_path: Path, request: pytest.FixtureRequest
) -> tuple[Path, Path, dict[str, str], str]:
    if os.name == "nt":
        pytest.skip("AppImage staging and launch require POSIX shell and symlinks")
    extras = str(request.param)
    home = tmp_path / "home"
    home.mkdir()
    tools = tmp_path / "tools"
    tools.mkdir()
    uv = tools / "uv"
    main_source = (
        "import json, os, sys\n"
        "def main():\n"
        "    print(json.dumps({'argv': sys.argv, 'env': dict(os.environ)}))\n"
    )
    uv.write_text(
        f"#!{sys.executable}\n"
        "import json, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "if args[:2] == ['python', 'install']:\n"
        "    root = pathlib.Path(args[args.index('--install-dir') + 1])\n"
        "    binary = root / 'cpython-3.12-test-linux-x86_64-gnu/bin/python3'\n"
        "    binary.parent.mkdir(parents=True)\n"
        "    binary.symlink_to(sys.executable)\n"
        f"    for name in {(*_INSTALLER_FILES, *_RUNTIME_FILES)!r}:\n"
        "        path = binary.parent.parent / name\n"
        "        path.parent.mkdir(parents=True, exist_ok=True)\n"
        "        path.write_text('runtime fixture')\n"
        "elif args[:2] == ['pip', 'install']:\n"
        "    target = pathlib.Path(args[args.index('--target') + 1])\n"
        "    (target / 'install.json').write_text(json.dumps(args))\n"
        "    main = target / 'voz/interfaces/cli/main.py'\n"
        "    main.parent.mkdir(parents=True)\n"
        f"    main.write_text({main_source!r})\n"
        "else:\n"
        "    raise SystemExit('Unexpected uv invocation')\n",
        encoding="utf-8",
    )
    uv.chmod(0o755)
    tool = tools / "appimagetool"
    tool.write_text(
        "#!/bin/sh\nset -eu\n"
        'test "$1" = --appimage-extract-and-run\n'
        'test "$ARCH" = x86_64\n'
        'test -x "$2/AppRun"\n'
        'printf "AppImage tool stub\\n" > "$3"\n',
        encoding="utf-8",
    )
    tool.chmod(0o755)
    wheel = tmp_path / "voz_transcriber-0.1.0-py3-none-any.whl"
    wheel.touch()
    work = tmp_path / "work with spaces"
    env = {
        "HOME": str(home),
        "XDG_DATA_HOME": str(home / "data"),
        "XDG_CACHE_HOME": str(home / "cache"),
        "XDG_CONFIG_HOME": str(home / "config"),
        "XDG_STATE_HOME": str(home / "state"),
        "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}",
        "VOZ_WORK": str(work),
        "VOZ_OUT": str(tmp_path / "out"),
        "VOZ_EXTRAS": extras,
        "VOZ_FFMPEG_DIR": "",
        "APPIMAGETOOL": str(tool),
    }
    result = subprocess.run(
        ["bash", str(ROOT / "packaging/appimage/build.sh"), str(wheel)],
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (appdir,) = work.glob("*.AppDir")
    return appdir, wheel, env, extras


def test_common_desktop_resources_use_v_brand() -> None:
    desktop = configparser.ConfigParser(interpolation=None)
    desktop.read(ROOT / "packaging/common/v.desktop")
    entry = desktop["Desktop Entry"]
    assert entry["Name"] == "V"
    assert entry["GenericName"] == "Local Voice AI"
    assert entry["Exec"] == "v"
    assert entry["Icon"] == "v"
    assert (ROOT / "packaging/common/v.svg").read_bytes() == (
        ROOT / "packaging/icons/voz.svg"
    ).read_bytes()


def test_appimage_stages_v_brand_and_preserves_distribution(
    staged_appimage: tuple[Path, Path, dict[str, str], str],
) -> None:
    appdir, wheel, env, extras = staged_appimage
    assert appdir.name == "V.AppDir"
    suffix = f"-{extras}" if extras else ""
    assert sorted(path.name for path in Path(env["VOZ_OUT"]).iterdir()) == [
        f"V-0.1.0{suffix}-x86_64.AppImage"
    ]
    desktop = configparser.ConfigParser(interpolation=None)
    desktop.read(appdir / "v.desktop")
    entry = desktop["Desktop Entry"]
    assert entry["Name"] == "V"
    assert entry["GenericName"] == "Local Voice AI"
    assert entry["Exec"] == "v"
    assert entry["Icon"] == "v"
    assert (appdir / "v.svg").read_bytes() == (
        ROOT / "packaging/icons/voz.svg"
    ).read_bytes()
    assert (appdir / ".DirIcon").readlink() == Path("v.svg")
    assert not (appdir / "voz.desktop").exists()
    assert not (appdir / "voz.svg").exists()
    installed = json.loads((appdir / "usr/lib/voz/install.json").read_text())
    expected_spec = (
        f"voz-transcriber[{extras}] @ file://{wheel}" if extras else str(wheel)
    )
    assert installed[-1] == expected_spec


def test_apprun_uses_v_entrypoint_preserving_arguments_and_private_environment(
    staged_appimage: tuple[Path, Path, dict[str, str], str],
) -> None:
    appdir, _, env, _ = staged_appimage
    arguments = ["--no-browser", "--port", "9876", "argument with spaces"]
    result = subprocess.run(
        [str(appdir / "AppRun"), *arguments],
        env={**env, "PYTHONPATH": "/untrusted/site", "PYTHONNOUSERSITE": "0"},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    launched = json.loads(result.stdout)
    assert launched["argv"] == ["v", *arguments]
    assert launched["env"]["PYTHONNOUSERSITE"] == "1"
    assert launched["env"]["PYTHONPATH"] == str(appdir / "usr/lib/voz")
    assert launched["env"]["PATH"].split(os.pathsep)[0] == str(appdir / "usr/bin")
    for name in (
        "HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_STATE_HOME",
    ):
        assert launched["env"][name] == env[name]


def test_appimage_omits_installers_without_mutating_the_runtime_source(
    staged_appimage: tuple[Path, Path, dict[str, str], str],
) -> None:
    appdir, _, env, _ = staged_appimage
    runtime = appdir / "usr/python"
    source = Path(env["VOZ_WORK"]) / "python-store/cpython-3.12-test-linux-x86_64-gnu"
    for name in _INSTALLER_FILES:
        assert (source / name).read_text() == "runtime fixture"
        assert not (runtime / name).exists()
    assert not (runtime / "lib/python3.12/site-packages/pip").exists()
    assert not (runtime / "lib/python3.12/site-packages/pip-26.2.1.dist-info").exists()
    assert not (runtime / "lib/python3.12/ensurepip").exists()
    for name in _RUNTIME_FILES:
        assert (runtime / name).read_bytes() == (source / name).read_bytes()
    assert (runtime / "bin/python3").is_symlink()
    assert (appdir / "AppRun").is_file()
