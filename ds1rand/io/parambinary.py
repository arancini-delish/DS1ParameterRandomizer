"""Byte-level editing of one DSR `.param` file, keeping every original row.

soulstruct's `Param` keeps only the first of rows sharing an ID (vanilla has a few; other mods add more, e.g. the fog
gate randomizer's scaling SpEffects 7240/7280/7320/7360 appear twice with different contents). Re-serializing through
it would silently drop those rows. `ParamBinary` instead keeps the original rows as bytes, patches fields in place,
adds and removes rows, and writes the file back in the same layout:

    0x00  u32 row names offset      0x04  u16 row data offset (0x30 + 12 * rows, capped at 0xFFFF)
    0x06  u16 unknown, u16 paramdef data version, u16 row count
    0x0C  param type (32 bytes)     0x2C  endianness, flags1, flags2, paramdef format version
    0x30  row table: (i32 ID, u32 data offset, u32 name offset) per row
    row data (fixed size per row), then null-terminated row names (name offset 0 = no name)

Rows are written stably sorted by ID, as soulstruct writes them (vanilla is not strictly sorted; sorted output is
boot-tested), so repeated IDs keep their relative order. Fields are packed with soulstruct's row type for the param (row unpack/repack is byte-identical for every vanilla row)
and addressed by paramdef name, as in `GameParams`. Rows with a repeated ID cannot be addressed and are never changed.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any

from soulstruct.base.params.param_row import ParamRow

from ds1rand.io.gameparam import _paramdef_fields

HEADER_SIZE = 0x30
ROW_POINTER_SIZE = 12


@dataclass
class _Row:
    id: int
    data: bytes
    name: bytes  # raw, without terminator; b"" for no name


class DuplicateRowError(KeyError):
    """The row ID appears more than once in this param."""


class ParamBinary:
    def __init__(self, data: bytes, row_type: type[ParamRow] | None = None):
        """`row_type` defaults to soulstruct's DSR row type for the param type named in the header."""
        if row_type is None:
            import soulstruct.darksouls1r.params.paramdef as paramdefs

            row_type = getattr(paramdefs, data[0x0C:0x2C].split(b"\0")[0].decode("ascii").strip())
        if data[0x2C] != 0 or data[0x2D] & 0xFC:
            raise ValueError("Only little-endian DS1 params without offset/data-offset flags are supported")
        self.header = bytearray(data[:HEADER_SIZE])
        self.row_type = row_type
        self.row_size = row_type.get_size()
        self.fields = _paramdef_fields(row_type)
        count = struct.unpack_from("<H", data, 0x0A)[0]
        self.rows: list[_Row] = []
        for i in range(count):
            row_id, data_offset, name_offset = struct.unpack_from("<iII", data, HEADER_SIZE + ROW_POINTER_SIZE * i)
            name = data[name_offset:data.index(b"\0", name_offset)] if name_offset else b""
            self.rows.append(_Row(row_id, bytes(data[data_offset:data_offset + self.row_size]), name))

    # Lookup.

    def ids(self) -> list[int]:
        return [row.id for row in self.rows]

    @property
    def duplicate_ids(self) -> set[int]:
        seen, dups = set(), set()
        for row in self.rows:
            (dups if row.id in seen else seen).add(row.id)
        return dups

    def __contains__(self, row_id: int) -> bool:
        return any(row.id == row_id for row in self.rows)

    def _row(self, row_id: int) -> _Row:
        matches = [row for row in self.rows if row.id == row_id]
        if not matches:
            raise KeyError(f"No row {row_id}")
        if len(matches) > 1:
            raise DuplicateRowError(f"Row {row_id} appears {len(matches)} times; it cannot be edited")
        return matches[0]

    def values(self, row_id: int) -> dict[str, Any]:
        row = self.row_type.from_bytes(self._row(row_id).data)
        return {field: getattr(row, attr) for field, attr in self.fields.items()}

    # Editing.

    def set_values(self, row_id: int, values: dict[str, Any]) -> None:
        target = self._row(row_id)
        row = self.row_type.from_bytes(target.data)
        for field, value in values.items():
            setattr(row, self.fields[field], value)
        target.data = row.to_bytes()

    def add_row(self, row_id: int, copy_from: int, values: dict[str, Any] | None = None) -> None:
        """Add a copy of `copy_from` (data and name) as `row_id`."""
        if row_id in self:
            raise KeyError(f"Row {row_id} already exists")
        source = self._row(copy_from)
        self.rows.append(_Row(row_id, source.data, source.name))
        if values:
            self.set_values(row_id, values)

    def remove_row(self, row_id: int) -> None:
        self.rows.remove(self._row(row_id))

    # Writing.

    def to_bytes(self) -> bytes:
        rows = sorted(self.rows, key=lambda row: row.id)
        count = len(rows)
        data_start = HEADER_SIZE + ROW_POINTER_SIZE * count
        names_start = data_start + self.row_size * count
        header = bytearray(self.header)
        struct.pack_into("<IH", header, 0, names_start, min(data_start, 0xFFFF))
        struct.pack_into("<H", header, 0x0A, count)
        table, names = bytearray(), bytearray()
        for i, row in enumerate(rows):
            name_offset = names_start + len(names) if row.name else 0
            if row.name:
                names += row.name + b"\0"
            table += struct.pack("<iII", row.id, data_start + self.row_size * i, name_offset)
        return bytes(header + table + b"".join(row.data for row in rows) + names)
