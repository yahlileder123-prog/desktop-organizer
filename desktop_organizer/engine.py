"""Decide where each loose desktop file goes, then move it."""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from desktop_organizer.storage import Config, TypeRule, app_dir

SKIP_NAMES = {"desktop.ini", "thumbs.db", "ehthumbs.db", ".ds_store"}
SKIP_SUFFIXES = {".lnk", ".url"}


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _protected_roots() -> list[Path]:
    """Places a download must never be filed into."""
    roots = [_project_root(), app_dir()]
    for key in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
        value = os.environ.get(key)
        if value:
            roots.append(Path(value))
    return roots


def _is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except (OSError, ValueError):
        return False
    return True


def _is_blocked(folder: Path) -> bool:
    try:
        resolved = folder.resolve()
    except OSError:
        return True
    if resolved == Path(resolved.anchor):
        return True
    return any(_is_inside(resolved, root) for root in _protected_roots())


@dataclass(frozen=True)
class Action:
    src: Path
    dst: Path
    dest_dir: Path
    reason: str


def plan(desktop: Path, config: Config) -> tuple[list[Action], list[Path]]:
    """Return files to move, and files that stay because nothing taught matches them."""
    actions: list[Action] = []
    staying: list[Path] = []
    reserved: set[str] = set()
    files = sorted(
        (path for path in desktop.iterdir() if _is_loose_file(path)),
        key=lambda path: path.name.casefold(),
    )
    for src in files:
        chosen = _destination(src, config, desktop)
        if chosen is None:
            staying.append(src)
            continue
        dest_dir, reason = chosen
        target = _unique_path(dest_dir / src.name, reserved)
        reserved.add(os.path.normcase(str(target)))
        actions.append(Action(src=src, dst=target, dest_dir=dest_dir, reason=reason))
    return actions, staying


def apply(actions: list[Action], desktop: Path) -> tuple[list[Action], list[tuple[Path, str]]]:
    """Move planned files. Returns what moved, and files that could not be moved."""
    done: list[Action] = []
    errors: list[tuple[Path, str]] = []
    for action in actions:
        if not _is_loose_file(action.src) or not _same_dir(action.src.parent, desktop):
            errors.append((action.src, "It is not a loose file on the desktop."))
            continue
        allowed = _usable_folder(str(action.dest_dir), desktop)
        if allowed is None or not _same_dir(action.dst.parent, allowed):
            errors.append((action.src, "That folder can't be used."))
            continue
        try:
            allowed.mkdir(parents=True, exist_ok=True)
            if not allowed.is_dir() or _is_blocked(allowed):
                raise OSError("blocked folder")
            target = action.dst if not action.dst.exists() else _unique_path(allowed / action.src.name, set())
            if not _same_dir(target.parent, allowed):
                raise OSError("target left the folder")
            shutil.move(str(action.src), str(target))
        except OSError:
            errors.append((action.src, "It may be open in another program."))
            continue
        done.append(Action(src=action.src, dst=target, dest_dir=allowed, reason=action.reason))
    return done, errors


def undo_moves(moves: list[dict], desktop: Path) -> tuple[list[dict], list[dict], list[str]]:
    """Put files back onto the desktop. Returns restored moves, moves still pending, and messages."""
    restored: list[dict] = []
    pending: list[dict] = []
    notes: list[str] = []
    for move in reversed(moves):
        src = Path(str(move.get("src", "")))
        dst = Path(str(move.get("dst", "")))
        if not _same_dir(src.parent, desktop) or _is_blocked(dst.parent):
            notes.append(f"Left {dst.name} where it is.")
            continue
        if not dst.is_file() or dst.is_symlink():
            notes.append(f"{src.name} is no longer in the folder, so it was left as it is.")
            continue
        try:
            target = src if not src.exists() else _unique_path(src, set())
            if not _same_dir(target.parent, desktop):
                raise OSError("restore left the desktop")
            shutil.move(str(dst), str(target))
        except OSError:
            pending.append(move)
            notes.append(f"Couldn't put {src.name} back. It may be open.")
            continue
        restored.append(move)
        if target != src:
            notes.append(f"{src.name} came back as {target.name}.")
    pending_dsts = {item["dst"] for item in pending}
    still_pending = [move for move in moves if move["dst"] in pending_dsts]
    return restored, still_pending, notes


def keyword_suggestion(filename: str) -> str:
    """Pick a reasonable word from a file name so teaching starts with something to edit."""
    stem = Path(filename).stem
    tokens = re.findall(r"[A-Za-z0-9]{2,}", stem)
    skip = {
        "the", "and", "for", "with", "from", "this", "that", "your", "notes",
        "note", "final", "draft", "copy", "new", "file", "doc", "document",
        "homework", "assignment",
    }
    useful = [token for token in tokens if token.casefold() not in skip]
    pool = useful or tokens
    if not pool:
        return ""
    return max(pool, key=len)


def type_for_extension(config: Config, suffix: str) -> TypeRule | None:
    suffix = suffix.casefold()
    for item in config.types:
        if suffix in item.extensions:
            return item
    return None


def _destination(src: Path, config: Config, desktop: Path) -> tuple[Path, str] | None:
    blob = _name_blob(src)
    best: tuple[tuple[int, int], Path, str] | None = None
    for index, rule in enumerate(config.rules):
        folder = _usable_folder(rule.folder, desktop)
        if folder is None:
            continue
        for word in rule.keywords:
            if _mentions(blob, word):
                score = (len(_phrase(word)), index)
                reason = f"the name mentions {word}"
                if best is None or score > best[0]:
                    best = (score, folder, reason)
    if best is not None:
        return best[1], best[2]

    suffix = src.suffix.casefold()
    for item in config.types:
        if not item.enabled or suffix not in item.extensions:
            continue
        folder = _usable_folder(item.folder, desktop)
        if folder is None:
            continue
        return folder, item.label
    return None


def _is_loose_file(path: Path) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    if path.name.casefold() in SKIP_NAMES or path.name.startswith("~$"):
        return False
    return path.suffix.casefold() not in SKIP_SUFFIXES


def _usable_folder(folder: str, desktop: Path) -> Path | None:
    text = folder.strip()
    if not text:
        return None
    candidate = Path(text)
    if not candidate.is_absolute():
        return None
    try:
        if candidate.exists() and not candidate.is_dir():
            return None
        if _same_dir(candidate, desktop) or _is_blocked(candidate):
            return None
    except OSError:
        return None
    return candidate


def _same_dir(left: Path, right: Path) -> bool:
    try:
        return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))
    except OSError:
        return False


def _name_blob(path: Path) -> str:
    return _phrase(path.stem)


def _phrase(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _mentions(blob: str, keyword: str) -> bool:
    phrase = _phrase(keyword)
    if len(phrase) < 2:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", blob) is not None


def _unique_path(path: Path, reserved: set[str]) -> Path:
    def taken(candidate: Path) -> bool:
        return candidate.exists() or os.path.normcase(str(candidate)) in reserved

    if not taken(path):
        return path
    number = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({number}){path.suffix}")
        if not taken(candidate):
            return candidate
        number += 1
