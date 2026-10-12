"""Desktop shortcut for V.

A ``.desktop`` file (Linux), a ``.lnk`` (Windows) or a minimal ``.app`` (macOS).

Two modes. From a source checkout it points at the ``Start-V-*`` launcher and
uses the icon in ``packaging/icons``. Installed as a tool (no checkout) it is
Linux only: ``Exec=v`` (or ``voz``) with the icon shipped in the package; the
desktop session must have that command on its ``PATH``. Only the standard
library and what each system ships (PowerShell, ``sips``, ``gio``).

The marker in the state directory records what the shortcut opens, so a moved
or deleted target shows up as *broken* and ``refresh()`` can regenerate it.
Shortcuts named ``VOZ`` (``voz.desktop``, ``VOZ.lnk``, ``VOZ.app``) from before
the rename are recognised, replaced on ``create()`` and removed by ``remove()``.
"""

from __future__ import annotations

import os
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from voz.application.ports.desktop_shortcut import DesktopShortcutError

NAME = "V"
LEGACY_NAME = "VOZ"
DESKTOP_FILE = "v.desktop"
LEGACY_DESKTOP_FILE = "voz.desktop"
TOOL_COMMANDS = ("v", "voz")
BUNDLE_IDENTIFIER = "org.voz.app"  # unchanged until the new app id is decided
OWNED_KEY = "X-V-Shortcut=true"
_LEGACY_EXEC = re.compile(r"^Exec=.*(Iniciar-Linux|start-v-linux)\.sh", re.MULTILINE)
MARKER_FILENAME = "desktop-shortcut.txt"
LAUNCHERS = {
    "linux": "start-v-linux.sh",
    "darwin": "Start-V-macOS.command",
    "win32": "Start-V-Windows.bat",
}
ICONS = {"linux": "voz.png", "darwin": "voz.png", "win32": "voz.ico"}
Run = Callable[..., "subprocess.CompletedProcess[str]"]


def checkout_root() -> Path:
    """Root of the source checkout this module lives in (may not be one)."""
    return Path(__file__).resolve().parents[3]


def default_desktop_directory(platform: str = sys.platform) -> Path:
    if platform.startswith("linux") and shutil.which("xdg-user-dir"):
        shown = subprocess.run(
            ["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, check=False
        ).stdout.strip()
        if shown:
            return Path(shown)
    return Path.home() / "Desktop"


def _abbreviate(path: Path) -> str:
    home = Path.home()
    try:
        return "~/" + path.relative_to(home).as_posix()
    except ValueError:
        return path.as_posix()


class LocalDesktopShortcut:
    def __init__(
        self,
        *,
        state_directory: Path,
        root: Path | None = None,
        platform: str = sys.platform,
        desktop_directory: Callable[[], Path] | None = None,
        data_home: Path | None = None,
        run: Run = subprocess.run,
        command_lookup: Callable[[str], str | None] | None = None,
    ) -> None:
        self._marker = Path(state_directory) / MARKER_FILENAME
        self._root = checkout_root() if root is None else Path(root)
        self._platform = "linux" if platform.startswith("linux") else platform
        self._desktop = desktop_directory or (
            lambda: default_desktop_directory(platform)
        )
        self._data_home = data_home
        self._run = run

        def which(name: str) -> str | None:
            return shutil.which(name)

        self._lookup: Callable[[str], str | None] = command_lookup or which

    # -- what can be opened --------------------------------------------------

    def _checkout_supported(self) -> bool:
        launcher = LAUNCHERS.get(self._platform)
        icon = ICONS.get(self._platform)
        return (
            launcher is not None
            and icon is not None
            and (self._root / "pyproject.toml").is_file()
            and (self._root / launcher).is_file()
            and (self._root / "packaging" / "icons" / icon).is_file()
        )

    def _tool_command(self) -> str | None:
        if self._platform != "linux":
            return None
        return next((n for n in TOOL_COMMANDS if self._lookup(n)), None)

    def supported(self) -> bool:
        return self._checkout_supported() or self._tool_command() is not None

    # -- marker: line 1 = file made, line 2 = ``target=`` what it opens --------

    def _read_marker(self) -> tuple[Path | None, str | None]:
        try:
            lines = self._marker.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None, None
        recorded = Path(lines[0].strip()) if lines and lines[0].strip() else None
        target = next(
            (line[7:].strip() for line in lines[1:] if line.startswith("target=")),
            None,
        )
        return recorded, target or None

    def _recorded(self) -> Path | None:
        return self._read_marker()[0]

    def _target_exists(self, target: str) -> bool:
        if os.sep in target or "/" in target:
            return Path(target).is_file()
        return self._lookup(target) is not None

    def _state(self) -> str:
        """``missing``, ``ok`` or ``broken`` (the file is there but opens nothing)."""
        recorded, target = self._read_marker()
        if recorded is None or not recorded.exists():
            return "missing"
        # A marker without a target is a shortcut from before V; refresh() renews it.
        if target is not None and not self._target_exists(target):
            return "broken"
        return "ok"

    def exists(self) -> bool:
        return self._state() == "ok"

    def broken(self) -> bool:
        return self._state() == "broken"

    def location(self) -> str | None:
        recorded = self._recorded()
        return (
            None if recorded is None or not recorded.exists() else _abbreviate(recorded)
        )

    # -- create / refresh / remove -------------------------------------------

    def create(self) -> str:
        if not self.supported():
            raise DesktopShortcutError(
                "V needs a checkout with launchers or the v command."
            )
        previous = self._recorded()
        try:
            if self._checkout_supported():
                if self._platform == "win32":
                    made, target = self._windows()
                elif self._platform == "darwin":
                    made, target = self._mac()
                else:
                    made, target = self._linux()
            else:
                made, target = self._linux_tool()
            self._remove_files(previous, legacy_only=True)
            self._marker.parent.mkdir(parents=True, exist_ok=True)
            self._marker.write_text(f"{made}\ntarget={target}\n", encoding="utf-8")
        except (OSError, subprocess.SubprocessError) as error:
            raise DesktopShortcutError("The shortcut could not be created.") from error
        return _abbreviate(made)

    def refresh(self) -> bool:
        """Regenerate a shortcut VOZ made earlier that is broken or predates V.

        Never creates one that was not there (the user may have removed it) and never
        raises: the composition root calls it at startup. Returns whether it rewrote it.
        """
        state = self._state()
        pre_v = self._read_marker()[1] is None  # marker written before targets existed
        if state == "missing" or (state == "ok" and not pre_v) or not self.supported():
            return False
        try:
            self.create()
        except DesktopShortcutError:
            return False
        return True

    def remove(self) -> None:
        """Delete the shortcut (every copy, V and VOZ names) and the marker."""
        try:
            self._remove_files(self._recorded(), legacy_only=False)
            self._marker.unlink(missing_ok=True)
        except OSError as error:
            raise DesktopShortcutError("The shortcut could not be removed.") from error

    def _applications(self) -> Path:
        return (
            self._data_home
            or Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
        ) / "applications"

    def _remove_files(self, recorded: Path | None, *, legacy_only: bool) -> None:
        """Delete the shortcuts of ours (only the VOZ-named ones if ``legacy_only``)."""
        directories = [self._desktop(), self._applications()]
        if recorded is not None and recorded.parent not in directories:
            directories.append(recorded.parent)
        names = {
            "linux": (DESKTOP_FILE, LEGACY_DESKTOP_FILE),
            "darwin": (f"{NAME}.app", f"{LEGACY_NAME}.app"),
            "win32": (f"{NAME}.lnk", f"{LEGACY_NAME}.lnk"),
        }.get(self._platform, ())
        for directory in directories:
            for name in names[1:] if legacy_only else names:
                path = directory / name
                if self._owned(path, recorded):
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()

    @staticmethod
    def _owned(path: Path, recorded: Path | None) -> bool:
        """Whether ``path`` is a shortcut V (or VOZ) made, not a file of the user."""
        if path == recorded and (path.exists() or path.is_symlink()):
            return True
        try:
            if path.suffix == ".desktop":
                text = path.read_text(encoding="utf-8")
                return OWNED_KEY in text or (
                    "Name=VOZ" in text and _LEGACY_EXEC.search(text) is not None
                )
            if path.suffix == ".app":
                with (path / "Contents" / "Info.plist").open("rb") as plist:
                    return plistlib.load(plist).get("CFBundleIdentifier") == (
                        BUNDLE_IDENTIFIER
                    )
        except (OSError, ValueError, plistlib.InvalidFileException):
            return False
        return False  # a .lnk is ours only when the marker says so

    # -- Linux ---------------------------------------------------------------

    def _write_entries(self, entry: str) -> Path:
        targets = [self._desktop(), self._applications()]  # GNOME hides desktop icons
        for directory in targets:
            directory.mkdir(parents=True, exist_ok=True)
            file = directory / DESKTOP_FILE
            file.write_text(entry, encoding="utf-8")
            file.chmod(0o755)
        on_desktop = targets[0] / DESKTOP_FILE
        if shutil.which("gio"):
            # Without this GNOME asks whether to trust the launcher before opening it.
            self._run(
                ["gio", "set", str(on_desktop), "metadata::trusted", "true"],
                capture_output=True,
                text=True,
                check=False,
            )
        return on_desktop

    def _linux(self) -> tuple[Path, str]:
        launcher = str(self._root / LAUNCHERS["linux"])
        quoted = launcher
        for character in '\\"`$':
            quoted = quoted.replace(character, "\\" + character)
        entry = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={NAME}\n"
            "Comment=Local audio and video transcription\n"
            "Comment[es]=Transcripción local de audio y video\n"
            f'Exec="{quoted.replace("%", "%%")}"\n'
            f"Path={self._root}\n"
            f"Icon={self._root / 'packaging' / 'icons' / ICONS['linux']}\n"
            "Terminal=true\n"
            "Categories=AudioVideo;Audio;\n"
            f"{OWNED_KEY}\n"
        )
        return self._write_entries(entry), launcher

    def _linux_tool(self) -> tuple[Path, str]:
        command = self._tool_command()
        assert command is not None  # supported() was checked by create()
        icon = Path(__file__).resolve().parents[1] / "static" / "icon-512.png"
        entry = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={NAME}\n"
            "Comment=Local audio and video transcription\n"
            "Comment[es]=Transcripción local de audio y video\n"
            f"Exec={command}\n"
            + (f"Icon={icon}\n" if icon.is_file() else "")
            + "Terminal=true\n"
            "Categories=AudioVideo;Audio;\n"
            f"{OWNED_KEY}\n"
        )
        return self._write_entries(entry), command

    # -- macOS ---------------------------------------------------------------

    def _mac(self) -> tuple[Path, str]:
        app = self._desktop() / f"{NAME}.app"
        contents = app / "Contents"
        (contents / "MacOS").mkdir(parents=True, exist_ok=True)
        (contents / "Resources").mkdir(exist_ok=True)
        # Opens the launcher in Terminal so the first-time setup stays visible.
        executable = contents / "MacOS" / "v"
        launcher = str(self._root / LAUNCHERS["darwin"])
        executable.write_text(
            f"#!/bin/sh\nopen {shlex.quote(launcher)}\n", encoding="utf-8"
        )
        executable.chmod(0o755)
        png = contents / "Resources" / "icon.png"
        shutil.copyfile(self._root / "packaging" / "icons" / ICONS["darwin"], png)
        # sips ships with macOS; without it the app just keeps the generic icon.
        self._run(
            [
                "sips",
                "-s",
                "format",
                "icns",
                str(png),
                "--out",
                str(png.with_suffix(".icns")),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        png.unlink()
        with (contents / "Info.plist").open("wb") as output:
            plistlib.dump(
                {
                    "CFBundleName": NAME,
                    "CFBundleDisplayName": NAME,
                    "CFBundleIdentifier": BUNDLE_IDENTIFIER,
                    "CFBundleExecutable": "v",
                    "CFBundleIconFile": "icon",
                    "CFBundlePackageType": "APPL",
                },
                output,
            )
        os.utime(app)  # Finder rereads the icon
        return app, launcher

    # -- Windows -------------------------------------------------------------

    def _windows(self) -> tuple[Path, str]:
        # PowerShell knows where the Desktop is even when OneDrive moved it; the
        # paths travel in environment variables so nothing needs escaping.
        script = (
            "$d = [Environment]::GetFolderPath('Desktop');"
            f"$r = Join-Path $d '{NAME}.lnk';"
            "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($r);"
            "$s.TargetPath = $env:VOZ_LAUNCHER;"
            "$s.WorkingDirectory = $env:VOZ_ROOT;"
            "$s.IconLocation = $env:VOZ_ICON;"
            "$s.Save();"
            "Write-Output $r"
        )
        launcher = str(self._root / LAUNCHERS["win32"])
        done = self._run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            env={
                **os.environ,
                "VOZ_LAUNCHER": launcher,
                "VOZ_ROOT": str(self._root),
                "VOZ_ICON": str(self._root / "packaging" / "icons" / ICONS["win32"]),
            },
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(done.stdout.strip()), launcher


__all__ = ["LocalDesktopShortcut", "checkout_root", "default_desktop_directory"]
