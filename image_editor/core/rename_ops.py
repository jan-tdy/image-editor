"""Pattern-based batch rename engine.

Pattern tokens (used with ``str.format``):
  {name}   original filename without extension, after case/find-replace
  {ext}    original extension, including the leading dot
  {n}      sequence number, zero-padded to ``digits``
  {date}   file's modification date, YYYYMMDD
  {parent} name of the containing folder
  {orig}   original filename, including extension, untouched
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DEFAULT_PATTERN = "{name}"

CASE_MODES = ("keep", "lower", "upper", "title", "capitalize")


@dataclass
class RenamePlan:
    pattern: str = DEFAULT_PATTERN
    start: int = 1
    step: int = 1
    digits: int = 3
    case: str = "keep"
    find: str = ""
    replace: str = ""
    use_regex: bool = False


@dataclass
class RenameResult:
    old_path: str
    new_name: str
    error: str | None = None


def apply_case(text: str, mode: str) -> str:
    if mode == "lower":
        return text.lower()
    if mode == "upper":
        return text.upper()
    if mode == "title":
        return text.title()
    if mode == "capitalize":
        return text.capitalize()
    return text


def apply_find_replace(text: str, find: str, replace: str, use_regex: bool) -> str:
    """Replace literal or regex matches.

    Raises ``ValueError`` when regular-expression matching is enabled with an
    invalid pattern.
    """
    if not find:
        return text
    if use_regex:
        try:
            return re.sub(find, replace, text)
        except re.error as exc:
            raise ValueError(f"Invalid regular expression: {exc}") from exc
    return text.replace(find, replace)


def preview_names(paths: list[str], plan: RenamePlan) -> list[RenameResult]:
    """Compute the new filename for each path without touching the disk."""
    results: list[RenameResult] = []
    for i, path in enumerate(paths):
        p = Path(path)
        stem = apply_case(p.stem, plan.case)
        try:
            stem = apply_find_replace(stem, plan.find, plan.replace, plan.use_regex)
        except ValueError as exc:
            results.append(RenameResult(path, p.name, error=str(exc)))
            continue

        index = plan.start + i * plan.step
        n_str = str(max(index, 0)).zfill(max(plan.digits, 0))
        try:
            mtime = os.path.getmtime(path)
            date_str = datetime.fromtimestamp(mtime).strftime("%Y%m%d")
        except OSError:
            date_str = ""

        tokens = {
            "name": stem,
            "ext": p.suffix,
            "n": n_str,
            "date": date_str,
            "parent": p.parent.name,
            "orig": p.name,
        }
        try:
            new_name = plan.pattern.format(**tokens)
        except (KeyError, IndexError, ValueError) as exc:
            results.append(RenameResult(path, p.name, error=f"Invalid pattern: {exc}"))
            continue

        if not new_name.strip():
            results.append(RenameResult(path, p.name, error="Pattern produced an empty name"))
            continue
        if not Path(new_name).suffix:
            new_name += p.suffix
        results.append(RenameResult(path, new_name))
    return results


def find_conflicts(results: list[RenameResult]) -> dict[str, list[str]]:
    """Return {conflicting_full_path: [source paths]} for names colliding
    either with each other or with an existing file outside the batch."""
    conflicts: dict[str, list[str]] = {}
    targets: dict[str, list[str]] = {}

    for result in results:
        if result.error:
            continue
        target = str(Path(result.old_path).parent / result.new_name)
        targets.setdefault(target, []).append(result.old_path)

    batch_sources = {r.old_path for r in results}
    for target, sources in targets.items():
        if len(sources) > 1:
            conflicts[target] = sources
            continue
        if os.path.exists(target) and os.path.abspath(target) not in {
            os.path.abspath(s) for s in batch_sources
        }:
            conflicts[target] = sources
    return conflicts
