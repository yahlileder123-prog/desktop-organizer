"""A desktop shortcut that organizes as soon as it is opened."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from desktop_organizer.paths import desktop

SHORTCUT_NAME = "Organize Desktop.lnk"


def shortcut_path(folder: Path | None = None) -> Path:
    return (folder or desktop()) / SHORTCUT_NAME


def interpreter() -> Path:
    """Prefer pythonw so the shortcut does not flash a console."""
    current = Path(sys.executable)
    if current.name.lower() == "python.exe":
        windowed = current.with_name("pythonw.exe")
        if windowed.exists():
            return windowed
    return current


def app_script() -> Path:
    return Path(__file__).resolve().parent.parent / "main.py"


def launch_target() -> tuple[Path, str, Path] | None:
    """Program to run, its arguments, and the working directory.

    A packaged app launches its own exe. A source checkout launches Python.
    """
    if getattr(sys, "frozen", False):
        program = Path(sys.executable)
        if not program.exists():
            return None
        return program, "--organize", program.parent
    script = app_script()
    if not script.exists():
        return None
    return interpreter(), f'"{script}" --organize', script.parent


def create_shortcut(folder: Path | None = None) -> str | None:
    """Create or refresh the shortcut. Returns an error message, or None."""
    launched = launch_target()
    if launched is None:
        return "Couldn't find the organizer program."
    link = shortcut_path(folder)
    target, arguments, work = launched
    icon = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "shell32.dll") + ",4"
    try:
        command = f"""
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut({_ps(str(link))})
$shortcut.TargetPath = {_ps(str(target))}
$shortcut.Arguments = {_ps(arguments)}
$shortcut.WorkingDirectory = {_ps(str(work))}
$shortcut.WindowStyle = 1
$shortcut.Description = {_ps("Put loose desktop files into the folders you taught")}
$shortcut.IconLocation = {_ps(icon)}
$shortcut.Save()
"""
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return "Couldn't create the shortcut."
    if completed.returncode != 0 or not link.exists():
        return "Couldn't create the shortcut."
    return None


def _ps(value: str) -> str:
    if any(char in value for char in "\r\n\x00"):
        raise ValueError("unsafe path")
    return "'" + value.replace("'", "''") + "'"
