"""Writing a `RowStore` into the game's GameParam: always baseline + edits, never on top of earlier output.

`build_gameparam` loads the GameParam on disk, checks it against the vanilla baseline (refusing files modified by
something other than ds1rand unless `allow_modified`), restores every row to vanilla, then applies the store's
changes. New rows are created as soulstruct copies of the vanilla row they descend from, so padding bytes carry over,
and then given the store's values. `write_gameparam` saves the result and records the ds1rand marker next to it.
"""
from __future__ import annotations

from pathlib import Path

from ds1rand.alloc.store import RowStore
from ds1rand.baseline.compare import FileState, check_gameparam, restore_params, write_marker
from ds1rand.baseline.store import Baseline
from ds1rand.io.gameparam import GameParams


class ModifiedInstallError(RuntimeError):
    """The GameParam on disk was changed by something other than ds1rand."""


def apply_store(store: RowStore, params: GameParams) -> list[str]:
    """Apply every changed and new row of `store` to `params`; returns the params touched."""
    for param, rows in store.changes().items():
        for row_id, values in rows.items():
            if row_id not in params[param].rows:
                params.add_row(param, row_id, copy_from=store.source_of(param, row_id))
            params.set_row_values(param, row_id, values)
    return sorted(store.changes())


def build_gameparam(path: Path | str, baseline: Baseline, store: RowStore, allow_modified: bool = False) -> GameParams:
    params, report = check_gameparam(path, baseline)
    if report.state is FileState.MODIFIED and not allow_modified:
        raise ModifiedInstallError(f"GameParam was modified by another tool:\n{report.summary()}")
    restore_params(params, baseline)
    apply_store(store, params)
    return params


def write_gameparam(params: GameParams, path: Path | str, info: dict | None = None) -> list[str]:
    """Save and mark as written by ds1rand; returns the re-serialized params."""
    changed = params.save(path)
    write_marker(path, info)
    return changed
