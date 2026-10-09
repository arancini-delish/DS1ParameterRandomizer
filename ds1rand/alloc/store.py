"""`RowStore`: the working copy of param rows that the allocator and randomizers edit.

It starts as a base (the vanilla baseline, or the params as other mods left them) and records only the rows that
change, so output is always base + edits. Rows listed as `protected` (repeated IDs, which cannot be addressed) cannot
be edited or copied. Fields are paramdef names, as everywhere else.
"""
from __future__ import annotations

from typing import Any

from ds1rand.baseline.store import Baseline


class ProtectedRowError(KeyError):
    """The row cannot be edited (its ID appears more than once in the param, so it cannot be addressed)."""


class RowStore:
    def __init__(self, baseline: Baseline, protected: dict[str, set[int]] | None = None):
        self.baseline = baseline
        self.protected = {param: set(ids) for param, ids in (protected or {}).items()}
        self._edited: dict[str, dict[int, dict[str, Any]]] = {}
        self._new: dict[str, dict[int, int]] = {}  # param -> {new row ID: row it was copied from}

    def exists(self, param: str, row_id: int) -> bool:
        return row_id in self._edited.get(param, {}) or row_id in self.baseline.params[param].rows

    def values(self, param: str, row_id: int) -> dict[str, Any]:
        """Current field values of a row (a copy; use `set` to change them)."""
        if row_id in self._edited.get(param, {}):
            return dict(self._edited[param][row_id])
        return self.baseline.params[param].row_values(row_id)

    def set(self, param: str, row_id: int, values: dict[str, Any]) -> None:
        fields = self.baseline.params[param].fields
        unknown = set(values) - set(fields)
        if unknown:
            raise KeyError(f"{param} has no fields {sorted(unknown)}")
        self._check_editable(param, row_id)
        row = self.values(param, row_id)
        row.update(values)
        self._edited.setdefault(param, {})[row_id] = row

    def add(self, param: str, row_id: int, copy_from: int) -> None:
        """Add a new row as a copy of an existing one."""
        if self.exists(param, row_id):
            raise KeyError(f"{param} already has row {row_id}")
        self._check_editable(param, copy_from)
        self._edited.setdefault(param, {})[row_id] = self.values(param, copy_from)
        self._new.setdefault(param, {})[row_id] = self.source_of(param, copy_from)

    def _check_editable(self, param: str, row_id: int) -> None:
        if row_id in self.protected.get(param, set()):
            raise ProtectedRowError(f"{param} row {row_id} is protected")

    def is_new(self, param: str, row_id: int) -> bool:
        return row_id in self._new.get(param, {})

    def source_of(self, param: str, row_id: int) -> int:
        """The vanilla row a new row descends from (the row itself for vanilla rows)."""
        return self._new.get(param, {}).get(row_id, row_id)

    def changes(self) -> dict[str, dict[int, dict[str, Any]]]:
        """Param -> {row ID: full values} for new rows and rows that differ from the baseline."""
        result = {}
        for param, rows in self._edited.items():
            pb = self.baseline.params[param]
            changed = {
                row_id: dict(values)
                for row_id, values in rows.items()
                if row_id in self._new.get(param, {}) or values != pb.row_values(row_id)
            }
            if changed:
                result[param] = dict(sorted(changed.items()))
        return result
