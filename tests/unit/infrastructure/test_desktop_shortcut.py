"""Desktop shortcut adapter on temporary directories (never the real desktop)."""

from __future__ import annotations

import os
import plistlib
import shutil
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
    for entry in (desktop / "v.desktop", data / "applications" / "v.desktop"):
        text = entry.read_text(encoding="utf-8")
        assert "Name=V" in text
        assert f'Exec="{root}/start-v-linux.sh"' in text
        assert f"Icon={root}/packaging/icons/voz.png" in text
        assert f"Path={root}" in text
        assert "Terminal=true" in text
        assert entry.stat().st_mode & 0o111  # executable
    assert shortcut.exists()


def test_recreating_overwrites_and_exists_follows_the_file(tmp_path: Path) -> None:
    shortcut, desktop, _ = _shortcut(tmp_path, "linux")
    shortcut.create()
    (desktop / "v.desktop").write_text("stale")

    shortcut.create()

    assert "Name=V" in (desktop / "v.desktop").read_text(encoding="utf-8")
    (desktop / "v.desktop").unlink()
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
        for line in (desktop / "v.desktop").read_text(encoding="utf-8").splitlines()
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
        str(desktop / "v.desktop"),
        "metadata::trusted",
        "true",
    ]


def test_macos_builds_a_minimal_app_that_opens_the_launcher(tmp_path: Path) -> None:
    run = _Run()
    shortcut, desktop, _ = _shortcut(tmp_path, "darwin", run)

    shortcut.create()

    app = desktop / "V.app" / "Contents"
    script = (app / "MacOS" / "v").read_text(encoding="utf-8")
    assert "open" in script and "Start-V-macOS.command" in script
    assert (app / "MacOS" / "v").stat().st_mode & 0o111
    with (app / "Info.plist").open("rb") as plist:
        info = plistlib.load(plist)
    assert info["CFBundleExecutable"] == "v" and info["CFBundleName"] == "V"
    assert run.calls[0][0][0] == "sips"  # icns conversion, best effort
    assert shortcut.exists()


def test_windows_asks_powershell_for_a_lnk_to_the_bat_launcher(
    tmp_path: Path,
) -> None:
    lnk = tmp_path / "OneDrive" / "Escritorio" / "V.lnk"
    lnk.parent.mkdir(parents=True)
    lnk.write_bytes(b"lnk")
    run = _Run(stdout=f"{lnk}\r\n")
    shortcut, _, _ = _shortcut(tmp_path, "win32", run)

    shortcut.create()

    command, kwargs = run.calls[0]
    assert command[:4] == ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
    assert "CreateShortcut" in command[4] and "V.lnk" in command[4]
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
        state_directory=tmp_path / "state",
        root=wheel_like,
        platform="linux",
        command_lookup=lambda name: None,
    )
    assert not shortcut.supported()
    with pytest.raises(DesktopShortcutError):
        shortcut.create()

    shortcut, _, _ = _shortcut(tmp_path / "other", "freebsd")
    assert not shortcut.supported()
    assert not shortcut.broken() and shortcut.location() is None


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

    assert shortcut.create() == "~/Escritorio/v.desktop"
    assert shortcut.location() == "~/Escritorio/v.desktop"


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


def test_moving_the_checkout_makes_the_shortcut_broken_not_fine(
    tmp_path: Path,
) -> None:
    shortcut, desktop, _ = _shortcut(tmp_path, "linux")
    shortcut.create()
    assert shortcut.exists() and not shortcut.broken()

    (tmp_path / "Voz App").rename(tmp_path / "Moved")

    assert (desktop / "v.desktop").is_file()  # the file is still on the desktop
    assert not shortcut.exists()  # but it opens nothing
    assert shortcut.broken()
    assert shortcut.location() == str(desktop / "v.desktop")  # still listed to remove


def _at(
    tmp_path: Path, root: Path, *, desktop: Path | None = None
) -> LocalDesktopShortcut:
    """A shortcut sharing one state/desktop/data tree, running from ``root``."""
    shared = desktop or tmp_path / "desk"
    return LocalDesktopShortcut(
        state_directory=tmp_path / "state",
        root=root,
        platform="linux",
        desktop_directory=lambda: shared,
        data_home=tmp_path / "data",
        run=_Run(),
        command_lookup=lambda name: None,
    )


def test_refresh_regenerates_a_broken_shortcut_for_the_current_checkout(
    tmp_path: Path,
) -> None:
    old = _checkout(tmp_path / "old")
    new = _checkout(tmp_path / "new")
    _at(tmp_path, old).create()
    assert not _at(tmp_path, new).refresh()  # old one still opens: leave it alone
    desktop_file = tmp_path / "desk" / "v.desktop"
    assert str(old) in desktop_file.read_text(encoding="utf-8")

    shutil.rmtree(old)  # the old checkout disappears
    assert _at(tmp_path, new).broken()

    assert _at(tmp_path, new).refresh()

    for entry in (desktop_file, tmp_path / "data" / "applications" / "v.desktop"):
        assert str(new / "start-v-linux.sh") in entry.read_text(encoding="utf-8")
    assert _at(tmp_path, new).exists() and not _at(tmp_path, new).broken()
    assert not _at(tmp_path, new).refresh()  # healthy: nothing to do


def test_refresh_never_creates_a_shortcut_nobody_asked_for(tmp_path: Path) -> None:
    shortcut, desktop, data = _shortcut(tmp_path, "linux")

    assert shortcut.refresh() is False
    assert not desktop.exists() and not data.exists()

    shortcut.create()
    shortcut.remove()
    assert shortcut.refresh() is False  # the user removed it: stays removed


def test_refresh_swallows_failures_so_startup_cannot_crash(tmp_path: Path) -> None:
    old = _checkout(tmp_path / "old")
    _at(tmp_path, old).create()
    shutil.rmtree(old)
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("file")

    assert (
        _at(tmp_path, _checkout(tmp_path / "new"), desktop=blocked).refresh() is False
    )


def test_remove_deletes_both_copies_and_the_marker(tmp_path: Path) -> None:
    shortcut, desktop, data = _shortcut(tmp_path, "linux")
    shortcut.create()
    marker = tmp_path / "state" / "desktop-shortcut.txt"
    assert marker.is_file()
    unrelated = desktop / "notes.txt"
    unrelated.write_text("mine")

    shortcut.remove()

    assert not (desktop / "v.desktop").exists()
    assert not (data / "applications" / "v.desktop").exists()
    assert not marker.exists()
    assert unrelated.read_text() == "mine"
    assert not shortcut.exists() and not shortcut.broken()
    shortcut.remove()  # idempotent


def test_remove_leaves_a_desktop_file_of_the_user_alone(tmp_path: Path) -> None:
    shortcut, desktop, _ = _shortcut(tmp_path, "linux")
    desktop.mkdir(parents=True)
    (desktop / "v.desktop").write_text("[Desktop Entry]\nName=V\nExec=mine\n")

    shortcut.remove()

    assert (desktop / "v.desktop").read_text().endswith("Exec=mine\n")


LEGACY_ENTRY = (
    "[Desktop Entry]\nType=Application\nName=VOZ\n"
    'Exec="/old/place/Iniciar-Linux.sh"\nTerminal=true\n'
)


def _plant_pre_v_shortcut(tmp_path: Path) -> tuple[Path, Path]:
    desktop, applications = tmp_path / "Escritorio", tmp_path / "data-home/applications"
    for directory in (desktop, applications):
        directory.mkdir(parents=True)
        (directory / "voz.desktop").write_text(LEGACY_ENTRY)
    marker = tmp_path / "state" / "desktop-shortcut.txt"
    marker.parent.mkdir()
    marker.write_text(str(desktop / "voz.desktop"))  # old marker: one line
    return desktop, applications


def test_a_pre_v_shortcut_is_replaced_without_duplicates(tmp_path: Path) -> None:
    shortcut, _, _ = _shortcut(tmp_path, "linux")
    desktop, applications = _plant_pre_v_shortcut(tmp_path)
    assert shortcut.exists()  # it is there; refresh renews it

    assert shortcut.refresh()

    for directory in (desktop, applications):
        assert [p.name for p in directory.iterdir()] == ["v.desktop"]
    assert shortcut.exists() and not shortcut.refresh()


def test_remove_also_deletes_a_pre_v_shortcut(tmp_path: Path) -> None:
    shortcut, _, _ = _shortcut(tmp_path, "linux")
    desktop, applications = _plant_pre_v_shortcut(tmp_path)

    shortcut.remove()

    assert not list(desktop.iterdir()) and not list(applications.iterdir())


def test_installed_as_a_tool_the_entry_runs_the_command(tmp_path: Path) -> None:
    wheel_like = tmp_path / "site-packages"
    wheel_like.mkdir()
    desktop = tmp_path / "desk"
    found = {"v": "/usr/bin/v"}
    shortcut = LocalDesktopShortcut(
        state_directory=tmp_path / "state",
        root=wheel_like,
        platform="linux",
        desktop_directory=lambda: desktop,
        data_home=tmp_path / "data",
        run=_Run(),
        command_lookup=found.get,
    )
    assert shortcut.supported()

    shortcut.create()

    text = (desktop / "v.desktop").read_text(encoding="utf-8")
    assert "Name=V\n" in text and "Exec=v\n" in text
    assert "Path=" not in text and "Terminal=true" in text
    assert shortcut.exists()
    found.clear()  # `v` is uninstalled: the icon opens nothing
    assert shortcut.broken() and not shortcut.exists()
    found["voz"] = "/usr/bin/voz"  # `v` gone, `voz` still there
    assert shortcut.refresh()
    assert "Exec=voz\n" in (desktop / "v.desktop").read_text(encoding="utf-8")


def test_tool_mode_is_linux_only(tmp_path: Path) -> None:
    shortcut = LocalDesktopShortcut(
        state_directory=tmp_path / "state",
        root=tmp_path,
        platform="win32",
        command_lookup=lambda name: "/x/v",
    )
    assert not shortcut.supported()


def test_macos_remove_deletes_the_app_and_a_pre_v_bundle(tmp_path: Path) -> None:
    shortcut, desktop, _ = _shortcut(tmp_path, "darwin")
    shortcut.create()
    legacy = desktop / "VOZ.app" / "Contents"
    legacy.mkdir(parents=True)
    with (legacy / "Info.plist").open("wb") as output:
        plistlib.dump({"CFBundleIdentifier": "org.voz.app"}, output)
    (desktop / "Other.app").mkdir()

    shortcut.remove()

    assert [p.name for p in desktop.iterdir()] == ["Other.app"]


def test_windows_remove_deletes_only_the_recorded_lnk(tmp_path: Path) -> None:
    lnk = tmp_path / "OneDrive" / "Escritorio" / "V.lnk"
    lnk.parent.mkdir(parents=True)
    lnk.write_bytes(b"lnk")
    other = lnk.with_name("Otro.lnk")
    other.write_bytes(b"x")
    shortcut, _, _ = _shortcut(tmp_path, "win32", _Run(stdout=f"{lnk}\n"))
    shortcut.create()

    shortcut.remove()

    assert not lnk.exists() and other.exists()
    assert shortcut.location() is None


def test_remove_failures_are_typed_and_path_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shortcut, _, _ = _shortcut(tmp_path, "linux")
    shortcut.create()

    def fail(self: Path, *args: object, **kwargs: object) -> None:
        raise PermissionError(str(self))

    monkeypatch.setattr(Path, "unlink", fail)
    with pytest.raises(DesktopShortcutError) as failure:
        shortcut.remove()
    assert str(tmp_path) not in str(failure.value)


@pytest.mark.skipif(
    shutil.which("desktop-file-validate") is None,
    reason="desktop-file-validate (desktop-file-utils) is not installed",
)
@pytest.mark.parametrize("mode", ["checkout", "tool"])
def test_generated_desktop_entries_pass_desktop_file_validate(
    tmp_path: Path, mode: str
) -> None:
    desktop = tmp_path / "desk"
    root = _checkout(tmp_path) if mode == "checkout" else tmp_path / "wheel"
    root.mkdir(exist_ok=True)
    shortcut = LocalDesktopShortcut(
        state_directory=tmp_path / "state",
        root=root,
        platform="linux",
        desktop_directory=lambda: desktop,
        data_home=tmp_path / "data",
        run=_Run(),
        command_lookup=lambda name: "/usr/bin/v",
    )
    shortcut.create()

    for entry in (desktop / "v.desktop", tmp_path / "data/applications/v.desktop"):
        done = subprocess.run(
            ["desktop-file-validate", str(entry)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0 and not done.stdout and not done.stderr, done
