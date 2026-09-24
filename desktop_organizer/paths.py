"""Desktop and other Windows user folders."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

# Known Folder IDs. These follow OneDrive redirection, unlike Path.home() / "Desktop".
_FOLDERS = {
    "desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "music": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
    "pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
    "videos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
}

_FALLBACK = {
    "desktop": "Desktop",
    "documents": "Documents",
    "music": "Music",
    "pictures": "Pictures",
    "videos": "Videos",
}


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


def known_folder(name: str) -> Path | None:
    """Return a Windows known folder, or the usual home subfolder if the API fails."""
    fallback_name = _FALLBACK.get(name)
    fallback = Path.home() / fallback_name if fallback_name else None
    guid_text = _FOLDERS.get(name)
    if guid_text is None or os.name != "nt":
        return fallback if fallback and fallback.exists() else fallback

    try:
        ole32 = ctypes.windll.ole32
        shell32 = ctypes.windll.shell32
        ole32.CoInitialize(None)
        guid = _GUID()
        ole32.CLSIDFromString.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(_GUID)]
        ole32.CLSIDFromString.restype = ctypes.HRESULT
        if ole32.CLSIDFromString(guid_text, ctypes.byref(guid)) != 0:
            raise OSError("bad folder id")
        shell32.SHGetKnownFolderPath.argtypes = [
            ctypes.POINTER(_GUID),
            wintypes.DWORD,
            wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]
        shell32.SHGetKnownFolderPath.restype = ctypes.HRESULT
        pointer = ctypes.c_wchar_p()
        if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(pointer)) != 0:
            raise OSError("known folder unavailable")
        value = pointer.value
        if value:
            ole32.CoTaskMemFree(pointer)
            return Path(value)
    except (OSError, AttributeError):
        pass
    return fallback


def desktop() -> Path:
    folder = known_folder("desktop")
    if folder is None:
        return Path.home() / "Desktop"
    return folder


def pretty_path(path: str | Path) -> str:
    """Show a path relative to the user folder when that reads more clearly."""
    candidate = Path(path)
    try:
        relative = candidate.resolve().relative_to(Path.home().resolve())
    except (OSError, ValueError):
        return str(candidate)
    if str(relative) == ".":
        return "~"
    return "~\\" + str(relative)
