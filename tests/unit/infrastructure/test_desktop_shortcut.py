"""Desktop shortcut adapter on temporary directories (never the real desktop)."""

from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path

import pytest

from voz.application.ports.desktop_shortcut import (
    DesktopShortcut,
    DesktopShortcutError,
)
from voz.infrastructure.desktop_shortcut import (
    LAUNCHERS,
    LocalDesktopShortcut,
    checkout_root,
)


class _Run:
    def __init__(self, stdout: str = "") -> None:
        self.calls: list[tuple[list[str], dict[str, object]]] = []
        self.stdout = stdout

    def __call__(
        self, command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, self.stdout, "")


def _checkout(tmp_path: Path) -> Path:
    root = tmp_path / "Voz App"  # a space and no ASCII-only luck
    (root / "packaging" / "icons").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\n")
    for name in ("start-v-linux.sh", "Start-V-macOS.command", "Start-V-Windows.bat"):
        (root / name).write_text("#!/bin/sh\n")
    for name in ("voz.png", "voz.ico"):
        (root / "packaging" / "icons" / name).write_bytes(b"icon")
    return root


def _shortcut(
    tmp_path: Path, platform: str, run: _Run | None = None
) -> tuple[LocalDesktopShortcut, Path, Path]:
    desktop = tmp_path / "Escritorio"
    data = tmp_path / "data-home"
    shortcut = LocalDesktopShortcut(
        state_directory=tmp_path / "state",
        root=_checkout(tmp_path),
        platform=platform,
        desktop_directory=lambda: desktop,
        data_home=data,
        run=run or _Run(),
    )
    return shortcut, desktop, data


def test_linux_creates_desktop_and_menu_entries_for_the_launcher(
    tmp_path: Path,
) -> None:
    shortcut, desktop, data = _shortcut(tmp_path, "linux")
    assert isinstance(shortcut, DesktopShortcut)
    assert shortcut.supported() and not shortcut.exists()

    shortcut.create()

    root = tmp_path / "Voz App"
    for entry in (desktop / "voz.desktop", data / "applications" / "voz.desktop"):
        text = entry.read_text(encoding="utf-8")
        assert "Name=VOZ" in text
        assert f'Exec="{root}/start-v-linux.sh"' in text
        assert f"Icon={root}/packaging/icons/voz.png" in text
        assert f"Path={root}" in text
        assert "Terminal=true" in text
        assert entry.stat().st_mode & 0o111  # executable
    assert shortcut.exists()


def test_recreating_overwrites_and_exists_follows_the_file(tmp_path: Path) -> None:
    shortcut, desktop, _ = _shortcut(tmp_path, "linux")
    shortcut.create()
    (desktop / "voz.desktop").write_text("stale")

    shortcut.create()

    assert "Name=VOZ" in (desktop / "voz.desktop").read_text(encoding="utf-8")
    (desktop / "voz.desktop").unlink()
    assert not shortcut.exists()  # the user deleted the icon: offer to recreate it


@pytest.mark.skipif(os.name == "nt", reason='Windows forbids " in paths')
def test_exec_line_escapes_special_characters(tmp_path: Path) -> None:
    desktop = tmp_path / "desk"
    root = tmp_path / 'a"b$c%d'
    (root / "packaging" / "icons").mkdir(parents=True)
    (root / "pyproject.toml").write_text("")
    (root / "start-v-linux.sh").write_text("")
    (root / "packaging" / "icons" / "voz.png").write_bytes(b"x")
    shortcut = LocalDesktopShortcut(
        state_directory=tmp_path / "state",
        root=root,
        platform="linux",
        desktop_directory=lambda: desktop,
        data_home=tmp_path / "d",
        run=_Run(),
    )

    shortcut.create()

    exec_line = next(
        line
        for line in (desktop / "voz.desktop").read_text(encoding="utf-8").splitlines()
        if line.startswith("Exec=")
    )
    assert exec_line.endswith('a\\"b\\$c%%d/start-v-linux.sh"')


def test_linux_marks_the_desktop_file_as_trusted_when_gio_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def which(name: str) -> str:
        return "/usr/bin/gio"

    monkeypatch.setattr("shutil.which", which)
    run = _Run()
    shortcut, desktop, _ = _shortcut(tmp_path, "linux", run)

    shortcut.create()

    assert run.calls[0][0] == [
        "gio",
        "set",
        str(desktop / "voz.desktop"),
        "metadata::trusted",
        "true",
    ]


def test_macos_builds_a_minimal_app_that_opens_the_launcher(tmp_path: Path) -> None:
    run = _Run()
    shortcut, desktop, _ = _shortcut(tmp_path, "darwin", run)

    shortcut.create()

    app = desktop / "VOZ.app" / "Contents"
    script = (app / "MacOS" / "voz").read_text(encoding="utf-8")
    assert "open" in script and "Start-V-macOS.command" in script
    assert (app / "MacOS" / "voz").stat().st_mode & 0o111
    with (app / "Info.plist").open("rb") as plist:
        info = plistlib.load(plist)
    assert info["CFBundleExecutable"] == "voz" and info["CFBundleName"] == "VOZ"
    assert run.calls[0][0][0] == "sips"  # icns conversion, best effort
    assert shortcut.exists()


def test_windows_asks_powershell_for_a_lnk_to_the_bat_launcher(
    tmp_path: Path,
) -> None:
    lnk = tmp_path / "OneDrive" / "Escritorio" / "VOZ.lnk"
    lnk.parent.mkdir(parents=True)
    lnk.write_bytes(b"lnk")
    run = _Run(stdout=f"{lnk}\r\n")
    shortcut, _, _ = _shortcut(tmp_path, "win32", run)

    shortcut.create()

    command, kwargs = run.calls[0]
    assert command[:4] == ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
    assert "CreateShortcut" in command[4] and "VOZ.lnk" in command[4]
    env = kwargs["env"]
    assert isinstance(env, dict)
    root = tmp_path / "Voz App"
    assert env["VOZ_LAUNCHER"] == str(root / "Start-V-Windows.bat")
    assert env["VOZ_ICON"] == str(root / "packaging" / "icons" / "voz.ico")
    assert shortcut.exists()


def test_unsupported_when_there_is_no_checkout_or_launcher(tmp_path: Path) -> None:
    wheel_like = tmp_path / "site-packages"
    wheel_like.mkdir()
    shortcut = LocalDesktopShortcut(
        state_directory=tmp_path / "state", root=wheel_like, platform="linux"
    )
    assert not shortcut.supported()
    with pytest.raises(DesktopShortcutError):
        shortcut.create()

    shortcut, _, _ = _shortcut(tmp_path / "other", "freebsd")
    assert not shortcut.supported()


def test_io_failures_are_typed_and_path_free(tmp_path: Path) -> None:
    shortcut, desktop, _ = _shortcut(tmp_path, "linux")
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text("a file, not a directory")  # mkdir fails

    with pytest.raises(DesktopShortcutError) as failure:
        shortcut.create()

    assert str(tmp_path) not in str(failure.value)
    assert not shortcut.exists()


def test_location_hides_the_home_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    shortcut, _, _ = _shortcut(tmp_path, "linux")

    assert shortcut.create() == "~/Escritorio/voz.desktop"
    assert shortcut.location() == "~/Escritorio/voz.desktop"


def test_real_launchers_exist_and_old_names_delegate_to_them() -> None:
    root = checkout_root()
    assert set(LAUNCHERS.values()) == {
        "start-v-linux.sh",
        "Start-V-macOS.command",
        "Start-V-Windows.bat",
    }
    for name in LAUNCHERS.values():
        assert (root / name).is_file(), name
        if not name.endswith(".bat"):
            assert os.access(root / name, os.X_OK), name
    for old, new in (
        ("Iniciar-Linux.sh", "start-v-linux.sh"),
        ("Iniciar-Mac.command", "Start-V-macOS.command"),
        ("Iniciar-Windows.bat", "Start-V-Windows.bat"),
    ):
        text = (root / old).read_text()
        assert "DEPRECATED" in text and new in text, old
