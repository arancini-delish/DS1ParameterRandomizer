"""Reading and writing `GameParam.parambnd.dcx` through soulstruct.

Fields are addressed by their paramdef internal names (e.g. `atkId_Bullet`), matching `ds1paramdefs/`, not by
soulstruct's nicknames.

Saving only re-serializes params whose content changed since load. Untouched params keep their original bytes, so
quirks soulstruct cannot represent (notably repeated row IDs, which it drops) survive in params we never edit.
"""
from __future__ import annotations

import logging
import struct
from pathlib import Path
from typing import Any

from soulstruct.base.params.param import Param
from soulstruct.base.params.param_row import ParamRow
from soulstruct.darksouls1r.params import GameParamBND

_LOGGER = logging.getLogger(__name__)

# Offset of the u16 row count in a DSR .param header.
_ROW_COUNT_OFFSET = 0x0A


class _GameParamBND(GameParamBND):
    """Disables re-serializing every param on write; `GameParams.save` sets the entries itself."""

    def entry_autogen(self):
        pass


class DuplicateRowsLostError(RuntimeError):
    """Saving would re-serialize a param whose repeated row IDs soulstruct dropped on load."""


class GameParams:
    """All params from one `GameParam.parambnd.dcx`."""

    def __init__(self, bnd: _GameParamBND):
        self._bnd = bnd
        self._entries = {entry.stem: entry for entry in bnd.entries if entry.name.endswith(".param")}
        self._original = {stem: bytes(entry) for stem, entry in self._entries.items()}
        self._loaded = {stem: bytes(param) for stem, param in bnd.params.items()}
        # Param name -> number of rows soulstruct dropped on load because their row ID was repeated.
        self.duplicate_ids: dict[str, int] = {}
        for stem, data in self._original.items():
            dropped = struct.unpack_from("<H", data, _ROW_COUNT_OFFSET)[0] - len(bnd.params[stem])
            if dropped:
                self.duplicate_ids[stem] = dropped

    @classmethod
    def from_path(cls, path: Path | str) -> GameParams:
        # soulstruct warns once per repeated row ID; `duplicate_ids` records them instead.
        param_logger = logging.getLogger("soulstruct.base.params.param")
        level = param_logger.level
        param_logger.setLevel(logging.ERROR)
        try:
            return cls(_GameParamBND.from_path(path))
        finally:
            param_logger.setLevel(level)

    @property
    def names(self) -> list[str]:
        return list(self._bnd.params)

    def param(self, name: str) -> Param:
        """The soulstruct `Param` for `name` (e.g. "Bullet"). Rows are `param[row_id]`, fields `row["internalName"]`."""
        return self._bnd.params[name]

    __getitem__ = param

    def row(self, name: str, row_id: int) -> ParamRow:
        return self._bnd.params[name][row_id]

    def field_names(self, name: str) -> list[str]:
        """Internal names of the non-padding fields of `name`, in binary order."""
        row_type = self._bnd.params[name].ROW_TYPE
        return [meta.internal_name for meta in row_type.get_all_field_metadata().values() if not meta.is_pad]

    def row_values(self, name: str, row_id: int) -> dict[str, Any]:
        """Non-padding field values of a row, keyed by internal name."""
        row = self.row(name, row_id)
        return {field: row[field] for field in self.field_names(name)}

    def add_row(self, name: str, row_id: int, copy_from: int | None = None) -> ParamRow:
        """Add a row with default values, or a copy of row `copy_from`. Fails if `row_id` already exists."""
        param = self._bnd.params[name]
        if row_id in param.rows:
            raise KeyError(f"{name} already has row {row_id}")
        row = param.ROW_TYPE() if copy_from is None else param[copy_from].copy()
        param[row_id] = row
        return row

    def remove_row(self, name: str, row_id: int) -> None:
        self._bnd.params[name].pop(row_id)

    def next_free_id(self, name: str, start: int, end: int | None = None) -> int:
        """Lowest unused row ID in `[start, end)`, unbounded above if `end` is None."""
        rows = self._bnd.params[name].rows
        row_id = start
        while row_id in rows:
            row_id += 1
        if end is not None and row_id >= end:
            raise ValueError(f"No free {name} row ID in [{start}, {end})")
        return row_id

    def changed_params(self) -> list[str]:
        """Names of params whose content differs from load."""
        return [stem for stem, param in self._bnd.params.items() if bytes(param) != self._loaded[stem]]

    def save(self, path: Path | str, allow_dropping_duplicates: bool = False) -> list[str]:
        """Write the binder to `path` and return the names of the re-serialized params.

        Raises `DuplicateRowsLostError` if a changed param had repeated row IDs, unless `allow_dropping_duplicates`.
        """
        changed = self.changed_params()
        lossy = [stem for stem in changed if stem in self.duplicate_ids]
        if lossy and not allow_dropping_duplicates:
            raise DuplicateRowsLostError(f"Saving would drop rows with repeated IDs from: {', '.join(lossy)}")
        for stem, entry in self._entries.items():
            entry.set_uncompressed_data(bytes(self._bnd.params[stem]) if stem in changed else self._original[stem])
        self._bnd.write(path, force=True)
        _LOGGER.info("Wrote %s (re-serialized: %s)", path, ", ".join(changed) or "none")
        return changed
