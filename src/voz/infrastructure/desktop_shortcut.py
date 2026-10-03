"""Desktop shortcut for a VOZ checkout.

A ``.desktop`` file (Linux), a ``.lnk`` (Windows) or a minimal ``.app`` (macOS).

It points at the ``Iniciar-*`` launcher of the checkout and uses the icon in
``packaging/icons``. Only the standard library and what each system ships
(PowerShell, ``sips``, ``gio``). When VOZ is installed as a wheel there is no
checkout, so the feature reports ``supported = False``.
"""

from __future__ import annotations

import os
import plistlib
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from voz.application.ports.desktop_shortcut import DesktopShortcutError

NAME = "VOZ"
MARKER_FILENAME = "desktop-shortcut.txt"
LAUNCHERS = {
    "linux": "Iniciar-Linux.sh",
    "darwin": "Iniciar-Mac.command",
    "win32": "Iniciar-Windows.bat",
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
    ) -> None:
        self._marker = Path(state_directory) / MARKER_FILENAME
        self._root = checkout_root() if root is None else Path(root)
        self._platform = "linux" if platform.startswith("linux") else platform
        self._desktop = desktop_directory or (
            lambda: default_desktop_directory(platform)
        )
        self._data_home = data_home
        self._run = run

    def supported(self) -> bool:
        launcher = LAUNCHERS.get(self._platform)
        icon = ICONS.get(self._platform)
        return (
            launcher is not None
            and icon is not None
            and (self._root / "pyproject.toml").is_file()
            and (self._root / launcher).is_file()
            and (self._root / "packaging" / "icons" / icon).is_file()
        )

    def _recorded(self) -> Path | None:
        try:
            text = self._marker.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return Path(text) if text else None

    def exists(self) -> bool:
        recorded = self._recorded()
        return recorded is not None and recorded.exists()

    def location(self) -> str | None:
        recorded = self._recorded()
        return (
            None if recorded is None or not recorded.exists() else _abbreviate(recorded)
        )

    def create(self) -> str:
        if not self.supported():
            raise DesktopShortcutError(
                "VOZ does not run from a checkout with launchers."
            )
        try:
            if self._platform == "win32":
                made = self._windows()
            elif self._platform == "darwin":
                made = self._mac()
            else:
                made = self._linux()
            self._marker.parent.mkdir(parents=True, exist_ok=True)
            self._marker.write_text(str(made), encoding="utf-8")
        except (OSError, subprocess.SubprocessError) as error:
            raise DesktopShortcutError("The shortcut could not be created.") from error
        return _abbreviate(made)

    # -- Linux ---------------------------------------------------------------

    def _linux(self) -> Path:
        launcher = str(self._root / LAUNCHERS["linux"])
        for character in '\\"`$':
            launcher = launcher.replace(character, "\\" + character)
        entry = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={NAME}\n"
            "Comment=Transcripción local de audio y video\n"
            f'Exec="{launcher.replace("%", "%%")}"\n'
            f"Path={self._root}\n"
            f"Icon={self._root / 'packaging' / 'icons' / ICONS['linux']}\n"
            "Terminal=true\n"
            "Categories=AudioVideo;Audio;\n"
        )
        data = self._data_home or Path(
            os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
        )
        targets = [self._desktop(), data / "applications"]  # GNOME hides desktop icons
        for directory in targets:
            directory.mkdir(parents=True, exist_ok=True)
            file = directory / "voz.desktop"
            file.write_text(entry, encoding="utf-8")
            file.chmod(0o755)
        on_desktop = targets[0] / "voz.desktop"
        if shutil.which("gio"):
            # Without this GNOME asks whether to trust the launcher before opening it.
            self._run(
                ["gio", "set", str(on_desktop), "metadata::trusted", "true"],
                capture_output=True,
                text=True,
                check=False,
            )
        return on_desktop

    # -- macOS ---------------------------------------------------------------

    def _mac(self) -> Path:
        app = self._desktop() / f"{NAME}.app"
        contents = app / "Contents"
        (contents / "MacOS").mkdir(parents=True, exist_ok=True)
        (contents / "Resources").mkdir(exist_ok=True)
        # Opens the launcher in Terminal so the first-time setup stays visible.
        executable = contents / "MacOS" / "voz"
        executable.write_text(
            f"#!/bin/sh\nopen {shlex.quote(str(self._root / LAUNCHERS['darwin']))}\n",
            encoding="utf-8",
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
                    "CFBundleIdentifier": "org.voz.app",
                    "CFBundleExecutable": "voz",
                    "CFBundleIconFile": "icon",
                    "CFBundlePackageType": "APPL",
                },
                output,
            )
        os.utime(app)  # Finder rereads the icon
        return app

    # -- Windows -------------------------------------------------------------

    def _windows(self) -> Path:
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
        done = self._run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            env={
                **os.environ,
                "VOZ_LAUNCHER": str(self._root / LAUNCHERS["win32"]),
                "VOZ_ROOT": str(self._root),
                "VOZ_ICON": str(self._root / "packaging" / "icons" / ICONS["win32"]),
            },
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(done.stdout.strip())


__all__ = ["LocalDesktopShortcut", "checkout_root", "default_desktop_directory"]
