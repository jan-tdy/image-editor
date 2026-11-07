"""Photo Triage: queue/history logic and the batch plan for Keep/Favourite/Trash.

Nothing here touches the disk until :func:`execute_plan` is called, so the
whole review can be undone simply by closing the dialog.
"""
from __future__ import annotations

import os
import random
import shutil
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..constants import IMAGE_EXTENSIONS
from ..models.file_model import _natural_key

KEEP = "keep"
FAVOURITE = "favourite"
TRASH = "trash"
ACTIONS = (KEEP, FAVOURITE, TRASH)

ORDER_NAME = "name"
ORDER_DATE = "date"
ORDER_RANDOM = "random"
ORDERS = (ORDER_NAME, ORDER_DATE, ORDER_RANDOM)


def _capture_time(path: str) -> float:
    """EXIF DateTimeOriginal when readable, else the file's mtime."""
    try:
        from PIL import Image

        with Image.open(path) as img:
            exif = img.getexif()
            raw = exif.get_ifd(0x8769).get(0x9003) or exif.get(0x0132)
        if raw:
            return datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S").timestamp()
    except Exception:
        pass
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def collect_photos(folder: str, order: str = ORDER_NAME, descending: bool = False,
                   seed: int | None = None) -> list[str]:
    """Images directly inside ``folder`` in the requested order."""
    paths: list[str] = []
    try:
        with os.scandir(folder) as it:
            for item in it:
                if item.is_file() and Path(item.name).suffix.lower() in IMAGE_EXTENSIONS:
                    paths.append(item.path)
    except OSError:
        return []
    if order == ORDER_RANDOM:
        random.Random(seed).shuffle(paths)
        return paths
    if order == ORDER_DATE:
        paths.sort(key=lambda p: (_capture_time(p), _natural_key(os.path.basename(p))))
    else:
        paths.sort(key=lambda p: _natural_key(os.path.basename(p)))
    if descending:
        paths.reverse()
    return paths


def normalize_new_name(original_path: str, typed: str) -> str | None:
    """Validate a typed file name; returns it (extension restored if omitted)
    or ``None`` if it is empty / a path / otherwise unusable."""
    name = typed.strip()
    if not name or name in (".", "..") or "/" in name or "\\" in name or "\x00" in name:
        return None
    ext = Path(original_path).suffix
    if not Path(name).suffix:
        name += ext
    return name


class TriageSession:
    """Review state: undecided queue, back-history, decisions and renames."""

    def __init__(self, paths: list[str]):
        self.all_paths = list(paths)
        self.queue: deque[str] = deque(paths)
        self.history: list[str] = []
        self.decisions: dict[str, str] = {}
        self.renames: dict[str, str] = {}
        self.current: str | None = self.queue.popleft() if self.queue else None

    # -- state ---------------------------------------------------------
    @property
    def finished(self) -> bool:
        return self.current is None

    def can_go_back(self) -> bool:
        return bool(self.history)

    def remaining(self) -> int:
        """Photos still waiting for a decision (including the current one)."""
        pending = sum(1 for p in self.queue if p not in self.decisions)
        return pending + (1 if self.current is not None and self.current not in self.decisions else 0)

    def counts(self) -> dict[str, int]:
        out = {a: 0 for a in ACTIONS}
        for action in self.decisions.values():
            out[action] += 1
        return out

    def display_name(self, path: str) -> str:
        return self.renames.get(path) or os.path.basename(path)

    # -- navigation ----------------------------------------------------
    def _advance(self) -> None:
        self.current = self.queue.popleft() if self.queue else None

    def decide(self, action: str) -> None:
        if self.current is None or action not in ACTIONS:
            return
        self.decisions[self.current] = action
        self.history.append(self.current)
        self._advance()

    def defer(self) -> None:
        """Next: leave undecided and send to the end of the queue."""
        if self.current is None:
            return
        self.decisions.pop(self.current, None)
        if not self.queue:
            return  # the only photo left - nothing to rotate to
        self.history.append(self.current)
        self.queue.append(self.current)
        self._advance()

    def back(self) -> None:
        if not self.history:
            return
        prev = self.history.pop()
        if self.current is not None:
            # Re-queue it (decided or not) so stepping forward shows it again.
            self.queue.appendleft(self.current)
        try:
            self.queue.remove(prev)  # it may have been deferred to the end
        except ValueError:
            pass
        self.current = prev

    def resume(self) -> None:
        """Leave the finished state by stepping back to the last photo."""
        if self.current is None:
            self.back()

    def set_rename(self, path: str, typed: str) -> bool:
        name = normalize_new_name(path, typed)
        if name is None:
            return False
        if name == os.path.basename(path):
            self.renames.pop(path, None)
        else:
            self.renames[path] = name
        return True


@dataclass
class PlannedAction:
    src: str
    action: str
    dst: str | None  # None for Trash and for an untouched Keep
    new_name: str | None = None


def _unique(dest_dir: str, name: str, taken: set[str]) -> str:
    stem, ext = os.path.splitext(name)
    candidate, n = name, 1
    while os.path.normcase(os.path.join(dest_dir, candidate)) in taken or os.path.exists(
        os.path.join(dest_dir, candidate)
    ):
        candidate = f"{stem} ({n}){ext}"
        n += 1
    taken.add(os.path.normcase(os.path.join(dest_dir, candidate)))
    return os.path.join(dest_dir, candidate)


def build_plan(session: TriageSession, favourite_dir: str) -> list[PlannedAction]:
    """Turn decisions into concrete operations, in review order. Undecided
    photos are left alone (treated like Keep without a rename)."""
    plan: list[PlannedAction] = []
    taken: set[str] = set()
    for path in session.all_paths:
        action = session.decisions.get(path)
        new_name = session.renames.get(path)
        if action == TRASH:
            plan.append(PlannedAction(path, TRASH, None, None))
        elif action == FAVOURITE:
            dst = _unique(favourite_dir, new_name or os.path.basename(path), taken)
            plan.append(PlannedAction(path, FAVOURITE, dst, new_name))
        elif action == KEEP and new_name:
            dst = _unique(os.path.dirname(path), new_name, taken)
            plan.append(PlannedAction(path, KEEP, dst, new_name))
        elif action == KEEP:
            plan.append(PlannedAction(path, KEEP, None, None))
    return plan


@dataclass
class ExecuteResult:
    done: int = 0
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def execute_plan(plan: list[PlannedAction], trash_fn: Callable[[str], None] | None) -> ExecuteResult:
    result = ExecuteResult()
    for item in plan:
        try:
            if item.action == TRASH:
                if trash_fn is None:
                    raise RuntimeError("send2trash is not installed - file not deleted")
                trash_fn(item.src)
            elif item.dst:
                os.makedirs(os.path.dirname(item.dst), exist_ok=True)
                if os.path.exists(item.dst):
                    raise FileExistsError("target already exists")
                shutil.move(item.src, item.dst)
            else:
                continue
            result.done += 1
        except Exception as exc:
            result.errors.append(f"{os.path.basename(item.src)}: {exc}")
    return result
