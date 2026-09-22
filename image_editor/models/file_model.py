"""Folder listing and navigation helpers."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from ..constants import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS

_NUM_RE = re.compile(r"(\d+)")


def _natural_key(name: str):
    return [int(part) if part.isdigit() else part.lower() for part in _NUM_RE.split(name)]


@dataclass(frozen=True)
class MediaEntry:
    path: str
    is_video: bool

    @property
    def name(self) -> str:
        return os.path.basename(self.path)


def list_media(folder: str) -> list[MediaEntry]:
    """List images and videos directly inside ``folder``, naturally sorted."""
    entries: list[MediaEntry] = []
    try:
        with os.scandir(folder) as it:
            for item in it:
                if not item.is_file():
                    continue
                ext = Path(item.name).suffix.lower()
                if ext in IMAGE_EXTENSIONS:
                    entries.append(MediaEntry(item.path, is_video=False))
                elif ext in VIDEO_EXTENSIONS:
                    entries.append(MediaEntry(item.path, is_video=True))
    except OSError:
        return []
    entries.sort(key=lambda e: _natural_key(e.name))
    return entries


class FolderNavigator:
    """Tracks the current position within a folder's media list."""

    def __init__(self):
        self.folder: str | None = None
        self.entries: list[MediaEntry] = []
        self.index: int = -1

    def set_folder(self, folder: str, select_path: str | None = None) -> None:
        self.folder = folder
        self.entries = list_media(folder)
        if not select_path or not self.select(select_path):
            self.index = 0 if self.entries else -1

    def select(self, path: str) -> bool:
        path = os.path.abspath(path)
        for i, entry in enumerate(self.entries):
            if os.path.abspath(entry.path) == path:
                self.index = i
                return True
        return False

    def current(self) -> MediaEntry | None:
        if 0 <= self.index < len(self.entries):
            return self.entries[self.index]
        return None

    def has_next(self) -> bool:
        return self.index + 1 < len(self.entries)

    def has_prev(self) -> bool:
        return self.index > 0

    def next(self) -> MediaEntry | None:
        if self.has_next():
            self.index += 1
            return self.current()
        return None

    def prev(self) -> MediaEntry | None:
        if self.has_prev():
            self.index -= 1
            return self.current()
        return None

    def refresh(self) -> None:
        current_path = self.current().path if self.current() else None
        if not self.folder:
            return
        self.entries = list_media(self.folder)
        if current_path and self.select(current_path):
            return
        # The previously current file is gone (renamed/deleted elsewhere):
        # clamp to the nearest remaining entry instead of leaving a stale
        # or out-of-range index.
        if self.entries:
            self.index = min(max(self.index, 0), len(self.entries) - 1)
        else:
            self.index = -1
