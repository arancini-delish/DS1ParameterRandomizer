"""Reading and writing `GameParam.parambnd.dcx` through soulstruct.

Fields are addressed by their paramdef names as written in `ds1paramdefs/` (e.g. `atkId_Bullet`, `vowType0`), not by
soulstruct's nicknames. soulstruct's own internal names mostly match, but some carry stray whitespace or a bit-width
suffix (`hasTarget : 1`), so `field_names`, `row_values` and `set_row_values` translate; padding fields are excluded.
`row["name"]` on a soulstruct row works for the plain names only.

Saving only re-serializes params whose content changed since load. Untouched params keep their original bytes, so
quirks soulstruct cannot represent (notably repeated row IDs, which it drops) survive in params we never edit.
"""
from __future__ import annotations

import functools
import logging
import struct
from pathlib import Path
from typing import Any

from soulstruct.base.params.param import Param
from soulstruct.containers import Binder
from soulstruct.base.params.param_row import ParamRow
from soulstruct.darksouls1r.params import GameParamBND

_LOGGER = logging.getLogger(__name__)

# Offset of the u16 row count in a DSR .param header.
_ROW_COUNT_OFFSET = 0x0A


@functools.cache
def _paramdef_fields(row_type: type[ParamRow]) -> dict[str, str]:
    """Paramdef field name -> soulstruct attribute name, for non-padding fields in binary order."""
    fields = {}
    for attr, meta in row_type.get_all_field_metadata().items():
        # soulstruct flags byte padding with `is_pad` but bit padding only as a hidden "Null padding" field.
        if meta.is_pad or (meta.hide and meta.tooltip.startswith("Null padding")):
            continue
        fields[meta.internal_name.split(":")[0].strip()] = attr
    return fields


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
        return cls.from_bytes(Path(path).read_bytes())

    @classmethod
    def from_bytes(cls, data: bytes) -> GameParams:
        # soulstruct warns once per repeated row ID; `duplicate_ids` records them instead.
        param_logger = logging.getLogger("soulstruct.base.params.param")
        level = param_logger.level
        param_logger.setLevel(logging.ERROR)
        try:
            return cls(_GameParamBND.from_bytes(data))
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
        """Paramdef names of the non-padding fields of `name`, in binary order."""
        return list(_paramdef_fields(self._bnd.params[name].ROW_TYPE))

    def row_values(self, name: str, row_id: int) -> dict[str, Any]:
        """Non-padding field values of a row, keyed by paramdef name."""
        row = self.row(name, row_id)
        return {field: getattr(row, attr) for field, attr in _paramdef_fields(type(row)).items()}

    def set_row_values(self, name: str, row_id: int, values: dict[str, Any]) -> None:
        """Set fields of a row by paramdef name."""
        row = self.row(name, row_id)
        attrs = _paramdef_fields(type(row))
        for field, value in values.items():
            setattr(row, attrs[field], value)

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


class RawGameParam:
    """`GameParam.parambnd.dcx` as raw `.param` entries, for byte-level editing with `ParamBinary`: nothing is
    re-serialized through soulstruct, so rows with repeated IDs survive."""

    def __init__(self, binder: Binder):
        self._binder = binder
        self._entries = {entry.stem: entry for entry in binder.entries if entry.name.endswith(".param")}

    @classmethod
    def from_bytes(cls, data: bytes) -> RawGameParam:
        return cls(Binder.from_bytes(data))

    @property
    def names(self) -> list[str]:
        return list(self._entries)

    def param_bytes(self, name: str) -> bytes:
        return bytes(self._entries[name])

    def set_param_bytes(self, name: str, data: bytes) -> None:
        self._entries[name].set_uncompressed_data(data)

    def to_bytes(self) -> bytes:
        """The whole binder, DCX-compressed like the original."""
        return bytes(self._binder)
