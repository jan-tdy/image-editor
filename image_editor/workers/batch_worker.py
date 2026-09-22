"""Background execution of a batch rename/convert/resize/adjust job.

Runs on a QThread so a folder of hundreds of images doesn't freeze the UI.
Every file operation is logged as a :class:`BatchLogEntry` recording enough
information (``mode`` + optional ``backup_path``) that :func:`undo_batch`
can reverse the whole run afterwards, as long as backups were enabled for
any step that overwrites or discards original bytes.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QThread, pyqtSignal

from ..core import image_ops

RESIZE_MODES = ("none", "fit", "exact", "scale_pct")


@dataclass
class BatchFileJob:
    src_path: str
    is_video: bool = False
    new_name: str | None = None  # None => keep the original filename


@dataclass
class BatchSettings:
    do_rename: bool = False

    do_convert_resize: bool = False
    target_format: str | None = None  # e.g. ".jpg"; None = keep original extension
    resize_mode: str = "none"
    width: int = 0
    height: int = 0
    scale_pct: int = 100
    jpeg_quality: int = 90

    do_adjust: bool = False
    brightness: float = 0.0
    contrast: float = 0.0
    saturation: float = 0.0
    red: float = 0.0
    green: float = 0.0
    blue: float = 0.0

    do_rotate: bool = False
    rotate_degrees: int = 0  # one of 90, 180, 270
    flip_h: bool = False
    flip_v: bool = False

    output_mode: str = "overwrite"  # "overwrite" | "folder"
    output_folder: str = ""
    backup_before_overwrite: bool = True

    def needs_pixel_ops(self) -> bool:
        return bool(
            self.do_convert_resize or self.do_adjust or self.do_rotate or self.flip_h or self.flip_v
        )


@dataclass
class BatchLogEntry:
    src_path: str
    out_path: str = ""
    mode: str = "noop"  # noop|copied|renamed|overwritten|renamed_and_edited|skipped_video|error
    backup_path: str | None = None
    error: str | None = None


def _apply_pixel_ops(image, settings: BatchSettings):
    if settings.do_rotate and settings.rotate_degrees:
        for _ in range((settings.rotate_degrees // 90) % 4):
            image = image_ops.rotate90(image, clockwise=True)
    if settings.flip_h:
        image = image_ops.flip_horizontal(image)
    if settings.flip_v:
        image = image_ops.flip_vertical(image)
    if settings.do_adjust:
        image = image_ops.apply_adjustments(
            image,
            brightness=settings.brightness,
            contrast=settings.contrast,
            saturation=settings.saturation,
            red=settings.red,
            green=settings.green,
            blue=settings.blue,
        )
    if settings.do_convert_resize and settings.resize_mode != "none":
        if settings.resize_mode == "fit" and settings.width > 0 and settings.height > 0:
            image = image_ops.resize(image, (settings.width, settings.height), keep_aspect=True)
        elif settings.resize_mode == "exact" and settings.width > 0 and settings.height > 0:
            image = image_ops.resize(image, (settings.width, settings.height), keep_aspect=False)
        elif settings.resize_mode == "scale_pct" and settings.scale_pct != 100:
            pct = max(1, settings.scale_pct) / 100
            new_size = (max(1, round(image.width * pct)), max(1, round(image.height * pct)))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
    return image


def _save_image(image, out_path: Path, jpeg_quality: int) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs = {}
    ext = out_path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        image = image.convert("RGB")
        save_kwargs["quality"] = jpeg_quality
        save_kwargs["optimize"] = True
    elif ext == ".png":
        save_kwargs["optimize"] = True
    image.save(out_path, **save_kwargs)


def _resolve_out_path(job: BatchFileJob, settings: BatchSettings) -> Path:
    src = Path(job.src_path)
    name = job.new_name if (settings.do_rename and job.new_name) else src.name

    if settings.do_convert_resize and settings.target_format and not job.is_video:
        name = Path(name).stem + settings.target_format
    elif not Path(name).suffix:
        name = name + src.suffix

    if settings.output_mode == "folder" and settings.output_folder:
        return Path(settings.output_folder) / name
    return src.parent / name


def process_one(job: BatchFileJob, settings: BatchSettings) -> BatchLogEntry:
    src = Path(job.src_path)
    if not src.exists():
        return BatchLogEntry(job.src_path, error="Source file no longer exists")

    out_path = _resolve_out_path(job, settings)
    entry = BatchLogEntry(job.src_path, str(out_path))

    try:
        if job.is_video:
            if out_path == src:
                entry.mode = "noop"
            elif settings.output_mode == "folder":
                shutil.copy2(src, out_path)
                entry.mode = "copied"
            else:
                os.rename(src, out_path)
                entry.mode = "renamed"
            return entry

        pixel_changed = settings.needs_pixel_ops()
        rename_or_move = out_path != src

        if not pixel_changed:
            if not rename_or_move:
                entry.mode = "noop"
            elif settings.output_mode == "folder":
                shutil.copy2(src, out_path)
                entry.mode = "copied"
            else:
                if out_path.exists():
                    raise FileExistsError(f"{out_path} already exists")
                os.rename(src, out_path)
                entry.mode = "renamed"
            return entry

        image = image_ops.load_with_orientation(str(src))
        image = _apply_pixel_ops(image, settings)

        if settings.output_mode == "folder":
            _save_image(image, out_path, settings.jpeg_quality)
            entry.mode = "copied"
            return entry

        if not rename_or_move:
            if settings.backup_before_overwrite:
                backup_path = src.with_suffix(src.suffix + ".bak")
                shutil.copy2(src, backup_path)
                entry.backup_path = str(backup_path)
            _save_image(image, out_path, settings.jpeg_quality)
            entry.mode = "overwritten"
        else:
            if out_path.exists():
                raise FileExistsError(f"{out_path} already exists")
            _save_image(image, out_path, settings.jpeg_quality)
            if settings.backup_before_overwrite:
                backup_path = src.with_suffix(src.suffix + ".bak")
                os.replace(src, backup_path)
                entry.backup_path = str(backup_path)
            else:
                os.remove(src)
            entry.mode = "renamed_and_edited"
        return entry
    except Exception as exc:  # noqa: BLE001 - surfaced per-file to the user
        entry.error = str(exc)
        entry.mode = "error"
        return entry


class BatchWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finishedBatch = pyqtSignal(list)

    def __init__(self, jobs: list[BatchFileJob], settings: BatchSettings, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.settings = settings

    def run(self) -> None:
        log: list[BatchLogEntry] = []
        total = len(self.jobs)
        for i, job in enumerate(self.jobs):
            if self.isInterruptionRequested():
                break
            entry = process_one(job, self.settings)
            log.append(entry)
            self.progress.emit(i + 1, total, Path(job.src_path).name)
        self.finishedBatch.emit(log)


def undo_batch(log: list[BatchLogEntry]) -> list[str]:
    """Best-effort reversal of a completed batch run. Returns warning strings
    for any entry that could not be fully restored (only possible when the
    user disabled backups for a destructive step)."""
    warnings: list[str] = []
    for entry in reversed(log):
        try:
            if entry.mode in ("noop", "error"):
                continue
            src = Path(entry.src_path)
            out_path = Path(entry.out_path) if entry.out_path else None
            backup = Path(entry.backup_path) if entry.backup_path else None

            if entry.mode == "copied":
                if out_path and out_path.exists() and out_path != src:
                    out_path.unlink()
            elif entry.mode == "renamed":
                if out_path and out_path.exists():
                    os.rename(out_path, src)
            elif entry.mode == "overwritten":
                if backup and backup.exists():
                    shutil.move(str(backup), src)
                else:
                    warnings.append(f"{src.name}: no backup available, edit could not be undone")
            elif entry.mode == "renamed_and_edited":
                if out_path and out_path.exists():
                    out_path.unlink()
                if backup and backup.exists():
                    os.rename(backup, src)
                else:
                    warnings.append(f"{src.name}: no backup available, original could not be restored")
        except OSError as exc:
            warnings.append(f"{Path(entry.src_path).name}: undo failed ({exc})")
    return warnings
