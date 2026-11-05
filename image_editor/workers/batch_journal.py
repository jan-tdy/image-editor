"""On-disk undo journal for batch runs.

A finished batch is written as a hidden JSON file (``.image-editor-batch-*.json``)
in the folder where its outputs went, so the run can still be reverted after
the Batch dialog is closed or the app restarts. The journal stores the same
:class:`BatchLogEntry` records that :func:`undo_batch` consumes.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path

from .batch_worker import BatchFileJob, BatchLogEntry, BatchSettings, undo_batch

JOURNAL_VERSION = 1
JOURNAL_PREFIX = ".image-editor-batch-"
JOURNAL_SUFFIX = ".json"


def journal_directory(jobs: list[BatchFileJob], settings: BatchSettings) -> Path:
    """Folder the journal is written to: the output folder when there is one,
    otherwise the deepest folder containing every source file."""
    if settings.output_mode == "folder" and settings.output_folder:
        return Path(settings.output_folder)
    parents = [str(Path(job.src_path).parent) for job in jobs]
    if not parents:
        raise ValueError("No files were processed, so there is nothing to journal")
    try:
        return Path(os.path.commonpath(parents))
    except ValueError:  # e.g. files on different Windows drives
        return Path(parents[0])


def has_undoable_entries(log: list[BatchLogEntry]) -> bool:
    return any(e.mode not in ("noop", "error") for e in log)


def write_journal(log: list[BatchLogEntry], directory: Path) -> Path:
    """Write ``log`` as a new journal in ``directory`` and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    path = directory / f"{JOURNAL_PREFIX}{now.strftime('%Y%m%d-%H%M%S-%f')}{JOURNAL_SUFFIX}"
    payload = {
        "version": JOURNAL_VERSION,
        "created": now.isoformat(timespec="seconds"),
        "entries": [asdict(entry) for entry in log],
    }
    # Write to a temp file and rename, so a crash never leaves half a journal.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def read_journal(path: Path) -> list[BatchLogEntry]:
    """Load the entries of a journal. Raises ``ValueError`` if it is not one."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Not a valid batch journal: {exc}") from exc
    if not isinstance(data, dict) or data.get("version") != JOURNAL_VERSION:
        raise ValueError("Unsupported batch journal version")
    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError("Batch journal has no entries list")

    known = {f.name for f in fields(BatchLogEntry)}
    entries: list[BatchLogEntry] = []
    for raw in raw_entries:
        if not isinstance(raw, dict) or not isinstance(raw.get("src_path"), str):
            raise ValueError("Batch journal contains a malformed entry")
        entries.append(BatchLogEntry(**{k: v for k, v in raw.items() if k in known}))
    return entries


def undo_journal(path: Path) -> list[str]:
    """Revert the batch recorded in ``path``.

    The journal is deleted only when the undo finished without warnings, so a
    partial failure can still be retried. Returns the warnings from undo_batch.
    """
    path = Path(path)
    warnings = undo_batch(read_journal(path))
    if not warnings:
        path.unlink(missing_ok=True)
    return warnings
