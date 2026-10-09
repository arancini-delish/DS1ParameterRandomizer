"""Comparing game files on disk against the vanilla baseline, and restoring them to it.

Randomization always starts from the baseline: files on disk are loaded, compared, restored to baseline values, and only
then edited. Comparing first means foreign modifications (other mods) are reported instead of silently overwritten.
Files ds1rand wrote itself are recognised by a sidecar marker (`<file>.ds1rand.json`) holding their SHA-256.
"""
from __future__ import annotations

import enum
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ds1rand.baseline.store import Baseline, sha256_file
from ds1rand.io.gameparam import GameParams
from ds1rand.io.msg import ItemText

MARKER_SUFFIX = ".ds1rand.json"


@dataclass
class ParamDiff:
    name: str
    changed: dict[int, dict[str, tuple[Any, Any]]] = field(default_factory=dict)  # row -> field -> (baseline, disk)
    added: list[int] = field(default_factory=list)  # rows on disk, not in baseline
    removed: list[int] = field(default_factory=list)  # rows in baseline, not on disk
    duplicate_ids_changed: bool = False

    def __bool__(self) -> bool:
        return bool(self.changed or self.added or self.removed or self.duplicate_ids_changed)

    def summary(self) -> str:
        parts = [f"{len(self.changed)} changed", f"{len(self.added)} added", f"{len(self.removed)} removed"]
        if self.duplicate_ids_changed:
            parts.append("duplicate row IDs differ")
        return f"{self.name}: " + ", ".join(parts)


@dataclass
class TextDiff:
    fmg_id: int
    stem: str
    changed: dict[int, tuple[str | None, str | None]] = field(default_factory=dict)  # text_id -> (baseline, disk)

    def __bool__(self) -> bool:
        return bool(self.changed)

    def summary(self) -> str:
        return f"{self.stem} (FMG {self.fmg_id}): {len(self.changed)} strings differ"


def diff_params(params: GameParams, baseline: Baseline) -> list[ParamDiff]:
    """Differences of every param from the baseline. Params missing from either side raise `ValueError`."""
    if set(params.names) != set(baseline.params):
        raise ValueError(f"Param set differs from baseline: {sorted(set(params.names) ^ set(baseline.params))}")
    diffs = []
    for name, pb in baseline.params.items():
        disk = params[name].rows
        diff = ParamDiff(
            name,
            added=sorted(set(disk) - set(pb.rows)),
            removed=sorted(set(pb.rows) - set(disk)),
            duplicate_ids_changed=params.duplicate_ids.get(name, 0) != baseline.duplicate_ids.get(name, 0),
        )
        for row_id, values in pb.rows.items():
            if row_id not in disk:
                continue
            row = params.row_values(name, row_id)
            fields = {f: (v, row[f]) for f, v in zip(pb.fields, values) if row[f] != v}
            if fields:
                diff.changed[row_id] = fields
        if diff:
            diffs.append(diff)
    return diffs


def diff_text(text: ItemText, baseline: Baseline) -> list[TextDiff]:
    if set(text.fmg_ids) != set(baseline.text):
        raise ValueError(f"FMG set differs from baseline: {sorted(set(text.fmg_ids) ^ set(baseline.text))}")
    diffs = []
    for fmg_id, (stem, base_entries) in baseline.text.items():
        disk_entries = text.fmg_entries(fmg_id)
        diff = TextDiff(fmg_id, stem)
        for text_id in base_entries.keys() | disk_entries.keys():
            if base_entries.get(text_id) != disk_entries.get(text_id):
                diff.changed[text_id] = (base_entries.get(text_id), disk_entries.get(text_id))
        if diff:
            diffs.append(diff)
    return diffs


def restore_params(params: GameParams, baseline: Baseline) -> list[str]:
    """Set every param row back to baseline values. Returns the names of params that changed.

    Params with vanilla duplicate row IDs cannot be fully restored (soulstruct drops the duplicates); if one of those
    differs, `GameParams.save` will refuse to write it.
    """
    restored = []
    for diff in diff_params(params, baseline):
        pb = baseline.params[diff.name]
        for row_id in diff.added:
            params.remove_row(diff.name, row_id)
        for row_id in diff.removed:
            params.add_row(diff.name, row_id)
        for row_id in diff.removed + list(diff.changed):
            params.set_row_values(diff.name, row_id, pb.row_values(row_id))
        restored.append(diff.name)
    return restored


def restore_text(text: ItemText, baseline: Baseline) -> list[int]:
    """Set every FMG back to baseline strings. Returns the FMG entry IDs that changed."""
    restored = [diff.fmg_id for diff in diff_text(text, baseline)]
    for fmg_id in restored:
        text.set_fmg_entries(fmg_id, baseline.text[fmg_id][1])
    return restored


def marker_path(path: Path | str) -> Path:
    path = Path(path)
    return path.with_name(path.name + MARKER_SUFFIX)


def write_marker(path: Path | str, info: dict[str, Any] | None = None) -> None:
    """Record that ds1rand wrote the file at `path` (call right after writing it)."""
    data = {"sha256": sha256_file(path), **(info or {})}
    marker_path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def written_by_us(path: Path | str) -> bool:
    """True if `path` is unchanged since ds1rand wrote it."""
    marker = marker_path(path)
    if not marker.is_file():
        return False
    return json.loads(marker.read_text(encoding="utf-8")).get("sha256") == sha256_file(path)


class FileState(enum.Enum):
    VANILLA = "vanilla"  # matches the baseline
    OURS = "ours"  # written by ds1rand and unchanged since; safe to restore
    MODIFIED = "modified"  # differs from the baseline and not written by ds1rand


@dataclass
class FileReport:
    path: Path
    state: FileState
    diffs: list[ParamDiff] | list[TextDiff]

    def summary(self) -> str:
        lines = [f"{self.path.name}: {self.state.value}"]
        lines += [f"  {diff.summary()}" for diff in self.diffs]
        return "\n".join(lines)


def check_gameparam(path: Path | str, baseline: Baseline) -> tuple[GameParams, FileReport]:
    params = GameParams.from_path(path)
    return params, _report(Path(path), diff_params(params, baseline))


def check_item_text(path: Path | str, baseline: Baseline) -> tuple[ItemText, FileReport]:
    text = ItemText.from_path(path)
    return text, _report(Path(path), diff_text(text, baseline))


def _report(path: Path, diffs: list) -> FileReport:
    if not diffs:
        state = FileState.VANILLA
    elif written_by_us(path):
        state = FileState.OURS
    else:
        state = FileState.MODIFIED
    return FileReport(path, state, diffs)
