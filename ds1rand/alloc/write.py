"""Writing ds1rand's edits on top of whatever the other mods left (see docs/MOD_COMPAT.md).

ds1rand runs last (item -> enemy -> fog gate -> ds1rand). The *base* of a file is its state before ds1rand touched it:
the other mods' output, or vanilla. Edits are written as field-level patches onto the base, using `ParamBinary`, so
nothing is re-serialized through soulstruct and rows with repeated IDs survive.

Each written file gets two companions:
    <file>.ds1rand-base   the base it was built from
    <file>.ds1rand.json   marker: SHA-256 of the written file and of the base, and every patch (old and new value of
                          each patched field / string, and the rows ds1rand added)

`resolve_base` picks the base for the next run:
    no marker                          the file on disk is the base ("external")
    file unchanged since our write     the saved base ("rebuilt")
    file changed after our write       another mod ran on top of our output: our patches are stripped from the file on
                                       disk (each field still holding our value goes back to its old value; rows we
                                       added are removed) and the result is the base ("stripped"). Fields another mod
                                       changed since keep that mod's value and are reported as conflicts.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ds1rand.alloc.store import RowStore
from ds1rand.baseline.compare import marker_path
from ds1rand.baseline.store import sha256_file
from ds1rand.io.gameparam import RawGameParam
from ds1rand.io.msg import ItemText
from ds1rand.io.parambinary import ParamBinary

BASE_SUFFIX = ".ds1rand-base"
MARKER_FORMAT = 2


def base_path(path: Path | str) -> Path:
    path = Path(path)
    return path.with_name(path.name + BASE_SUFFIX)


def read_marker(path: Path | str) -> dict | None:
    marker = marker_path(path)
    return json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else None


@dataclass
class BaseResolution:
    data: bytes
    state: str  # "external", "rebuilt" or "stripped"
    conflicts: list[str] = field(default_factory=list)


def resolve_base(path: Path | str, strip: Callable[[bytes, dict], tuple[bytes, list[str]]]) -> BaseResolution:
    path = Path(path)
    marker = read_marker(path)
    if marker is None or marker.get("format") != MARKER_FORMAT:
        return BaseResolution(path.read_bytes(), "external")
    saved = base_path(path)
    if sha256_file(path) == marker["sha256"] and saved.is_file() and sha256_file(saved) == marker["base_sha256"]:
        return BaseResolution(saved.read_bytes(), "rebuilt")
    data, conflicts = strip(path.read_bytes(), marker["patches"])
    return BaseResolution(data, "stripped", conflicts)


def write_output(path: Path | str, data: bytes, base: bytes, patches: dict, info: dict | None = None) -> None:
    """Write `data` to `path`, the base it was built from to `<path>.ds1rand-base`, and the marker."""
    path = Path(path)
    path.write_bytes(data)
    base_path(path).write_bytes(base)
    marker = {
        "format": MARKER_FORMAT,
        "sha256": sha256_file(path),
        "base_sha256": sha256_file(base_path(path)),
        "patches": patches,
        **(info or {}),
    }
    marker_path(path).write_text(json.dumps(marker, indent=1) + "\n", encoding="utf-8")


# GameParam


def apply_params(base: bytes, store: RowStore) -> tuple[bytes, dict]:
    """Apply `store`'s changes to the base GameParam as field patches; returns the new file and the patch record
    {param: {"patched": {row: {field: [old, new]}}, "added": [rows]}}."""
    raw = RawGameParam.from_bytes(base)
    record: dict[str, dict[str, Any]] = {}
    for param, rows in store.changes().items():
        binary = ParamBinary(raw.param_bytes(param))
        patched, added = {}, []
        for row_id, values in rows.items():
            if store.is_new(param, row_id):
                source = store.source_of(param, row_id)
                old = binary.values(source)
                binary.add_row(row_id, copy_from=source)
                added.append(row_id)
            else:
                old = binary.values(row_id)
            changed = {f: v for f, v in values.items() if v != old[f]}
            if changed:
                binary.set_values(row_id, changed)
                if not store.is_new(param, row_id):
                    patched[str(row_id)] = {f: [old[f], v] for f, v in changed.items()}
        raw.set_param_bytes(param, binary.to_bytes())
        record[param] = {"patched": patched, "added": added}
    return raw.to_bytes(), record


def strip_params(data: bytes, record: dict) -> tuple[bytes, list[str]]:
    raw = RawGameParam.from_bytes(data)
    conflicts = []
    for param, changes in record.items():
        binary = ParamBinary(raw.param_bytes(param))
        for row_id in changes["added"]:
            if row_id in binary:
                binary.remove_row(row_id)
        for row, fields in changes["patched"].items():
            row_id = int(row)
            if row_id not in binary:
                conflicts.append(f"{param}[{row_id}] removed by another mod")
                continue
            current = binary.values(row_id)
            restore = {}
            for name, (old, new) in fields.items():
                if current[name] == new:
                    restore[name] = old
                else:
                    conflicts.append(f"{param}[{row_id}].{name}: changed by another mod after ds1rand ({new} -> "
                                     f"{current[name]}), kept")
            if restore:
                binary.set_values(row_id, restore)
        raw.set_param_bytes(param, binary.to_bytes())
    return raw.to_bytes(), conflicts


# Item text


def apply_text(base: bytes, patches: dict[tuple[str, int], str]) -> tuple[bytes, dict]:
    """Set item strings ((category, text ID) -> text) in base and patch FMGs; returns the new file and the record
    {fmg ID: {text ID: [old, new]}} (old None when the string did not exist)."""
    text = ItemText.from_bytes(base)
    record: dict[str, dict[str, list]] = {}
    for (category, text_id), string in sorted(patches.items()):
        for fmg_id in text._fmg_ids(category):
            old = text.fmg_entries(fmg_id).get(text_id)
            if old != string:
                record.setdefault(str(fmg_id), {})[str(text_id)] = [old, string]
        text.set(category, text_id, string)
    return text.to_bytes(), record


def strip_text(data: bytes, record: dict) -> tuple[bytes, list[str]]:
    text = ItemText.from_bytes(data)
    conflicts = []
    for fmg, strings in record.items():
        fmg_id = int(fmg)
        entries = text.fmg_entries(fmg_id)
        for tid, (old, new) in strings.items():
            text_id = int(tid)
            if entries.get(text_id) != new:
                conflicts.append(f"FMG {fmg_id}[{text_id}]: changed by another mod after ds1rand, kept")
            elif old is None:
                del entries[text_id]
            else:
                entries[text_id] = old
        text.set_fmg_entries(fmg_id, entries)
    return text.to_bytes(), conflicts
