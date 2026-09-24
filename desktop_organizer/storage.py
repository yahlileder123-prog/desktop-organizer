"""Where the teaching lives, and a record of the last moves so they can be undone."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


def app_dir() -> Path:
    root = os.environ.get("APPDATA") or str(Path.home())
    return Path(root) / "DesktopOrganizer"


def config_path() -> Path:
    return app_dir() / "config.json"


def history_path() -> Path:
    return app_dir() / "history.json"


@dataclass
class TypeRule:
    key: str
    label: str
    extensions: tuple[str, ...]
    enabled: bool = False
    folder: str = ""
    blurb: str = ""


@dataclass
class Rule:
    keywords: list[str]
    folder: str


@dataclass
class Config:
    rules: list[Rule] = field(default_factory=list)
    types: list[TypeRule] = field(default_factory=list)
    wizard_done: bool = False
    wizard_step: int = 0

    def type_by_key(self, key: str) -> TypeRule | None:
        for item in self.types:
            if item.key == key:
                return item
        return None

    def has_destination(self) -> bool:
        if any(rule.folder.strip() and rule.keywords for rule in self.rules):
            return True
        return any(item.enabled and item.folder.strip() for item in self.types)

    def add_keywords(self, keywords: list[str], folder: str) -> list[str]:
        """Send these words to a folder. A word only points at one folder.

        Returns the words that were saved.
        """
        folder = folder.strip()
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in keywords:
            text = " ".join(raw.split()).strip()
            if len(text) < 2:
                continue
            token = text.casefold()
            if token in seen:
                continue
            seen.add(token)
            cleaned.append(text)
        if not cleaned or not folder:
            return []

        folded = {word.casefold() for word in cleaned}
        for rule in self.rules:
            rule.keywords = [word for word in rule.keywords if word.casefold() not in folded]
        self.rules = [rule for rule in self.rules if rule.keywords]

        for rule in self.rules:
            if _same_folder(rule.folder, folder):
                existing = {word.casefold() for word in rule.keywords}
                for word in cleaned:
                    if word.casefold() not in existing:
                        rule.keywords.append(word)
                return cleaned

        self.rules.append(Rule(keywords=cleaned, folder=folder))
        return cleaned

    def remove_rule(self, index: int) -> None:
        if 0 <= index < len(self.rules):
            del self.rules[index]

    def set_type(self, key: str, *, folder: str | None = None, enabled: bool | None = None) -> None:
        item = self.type_by_key(key)
        if item is None:
            return
        if folder is not None:
            item.folder = folder.strip()
        if enabled is not None:
            item.enabled = enabled


def _same_folder(left: str, right: str) -> bool:
    return os.path.normcase(os.path.normpath(left.strip())) == os.path.normcase(os.path.normpath(right.strip()))


def default_types() -> list[TypeRule]:
    return [
        TypeRule("pdf", "PDFs", (".pdf",), blurb="Readings, forms, and other PDFs."),
        TypeRule(
            "images",
            "Pictures",
            (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".tif", ".tiff", ".svg"),
            blurb="Photos and screenshots.",
        ),
        TypeRule(
            "audio",
            "Audio",
            (".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".wma"),
            blurb="Music, voice notes, and other sound files.",
        ),
        TypeRule(
            "video",
            "Videos",
            (".mp4", ".mov", ".mkv", ".avi", ".wmv", ".webm", ".m4v"),
            blurb="Clips and recordings.",
        ),
        TypeRule(
            "documents",
            "Documents",
            (".doc", ".docx", ".txt", ".rtf", ".odt"),
            blurb="Word files, text, and other writing that is not a PDF.",
        ),
        TypeRule(
            "spreadsheets",
            "Spreadsheets",
            (".xls", ".xlsx", ".csv", ".ods"),
            blurb="Sheets and tables.",
        ),
        TypeRule(
            "presentations",
            "Presentations",
            (".ppt", ".pptx", ".odp"),
            blurb="Slide decks.",
        ),
        TypeRule(
            "archives",
            "Archives",
            (".zip", ".rar", ".7z", ".tar", ".gz"),
            blurb="Zip files and other bundles.",
        ),
        TypeRule(
            "installers",
            "Installers",
            (".exe", ".msi"),
            enabled=False,
            blurb="Setup programs. Left on the desktop until you turn this on.",
        ),
    ]


def fresh_config() -> Config:
    return Config(types=default_types())


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


def save_config(config: Config, path: Path | None = None) -> None:
    path = path or config_path()
    payload = {
        "version": 1,
        "wizard_done": config.wizard_done,
        "wizard_step": config.wizard_step,
        "rules": [{"keywords": rule.keywords, "folder": rule.folder} for rule in config.rules],
        "types": [
            {
                "key": item.key,
                "enabled": item.enabled,
                "folder": item.folder,
            }
            for item in config.types
        ],
    }
    _atomic_write(path, payload)


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    config = fresh_config()
    if not path.exists():
        return config
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return config
    if not isinstance(raw, dict):
        return config

    config.wizard_done = bool(raw.get("wizard_done", False))
    try:
        config.wizard_step = max(0, int(raw.get("wizard_step", 0)))
    except (TypeError, ValueError):
        config.wizard_step = 0

    by_key = {item.key: item for item in config.types}
    for entry in raw.get("types", []):
        if not isinstance(entry, dict):
            continue
        item = by_key.get(entry.get("key"))
        if item is None:
            continue
        item.enabled = bool(entry.get("enabled", False))
        folder = entry.get("folder", "")
        item.folder = folder if isinstance(folder, str) else ""

    rules: list[Rule] = []
    for entry in raw.get("rules", []):
        if not isinstance(entry, dict):
            continue
        folder = entry.get("folder", "")
        words = entry.get("keywords", [])
        if not isinstance(folder, str) or not isinstance(words, list):
            continue
        keywords = [word.strip() for word in words if isinstance(word, str) and word.strip()]
        if keywords and folder.strip():
            rules.append(Rule(keywords=keywords, folder=folder.strip()))
    config.rules = rules
    return config


def record_moves(moves: list[tuple[str, str]], path: Path | None = None) -> None:
    """Remember a finished organize so Undo can put those files back."""
    path = path or history_path()
    history = _load_history(path)
    history.append(
        {
            "created": datetime.now().isoformat(timespec="seconds"),
            "undone": False,
            "moves": [{"src": src, "dst": dst} for src, dst in moves],
        }
    )
    _save_history(history[-15:], path)


def latest_batch(path: Path | None = None) -> dict | None:
    path = path or history_path()
    for batch in reversed(_load_history(path)):
        if not batch.get("undone") and batch.get("moves"):
            return batch
    return None


def mark_batch(batch: dict, path: Path | None = None) -> None:
    """Write back a batch we already loaded, matching it by its timestamp."""
    path = path or history_path()
    history = _load_history(path)
    for index, existing in enumerate(history):
        if existing.get("created") == batch.get("created"):
            history[index] = batch
            break
    _save_history(history, path)


def _save_history(history: list[dict], path: Path) -> None:
    _atomic_write(path, {"batches": history})


def _load_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(raw, dict):
        raw = raw.get("batches", [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]
