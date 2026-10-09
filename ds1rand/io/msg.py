"""Reading and writing item text (`item.msgbnd.dcx`) through soulstruct.

DSR stores most item text categories twice: a base FMG and a 'patch' FMG with the same name, and the game shows the
patch string when one exists. Reads therefore prefer the patch FMG, and writes go to both so neither copy is stale.
"""
from __future__ import annotations

from pathlib import Path

from soulstruct.base.text.fmg import FMG
from soulstruct.darksouls1r.text.msg_directory import MSGDirectory
from soulstruct.darksouls1r.text.msgbnd import MSGBND

# Category name (FMG stem without the trailing underscore) -> base FMG entry ID.
CATEGORIES: dict[str, int] = {
    stem.rstrip("_"): entry_id
    for (bnd, entry_id), stem in MSGDirectory.DEFAULT_ENTRY_STEMS.items()
    if bnd == "item" and entry_id < 100
}
# Base FMG entry ID -> patch FMG entry ID.
_PATCH_IDS: dict[int, int] = {
    base_id: patch_id for (bnd, base_id), (_, patch_id) in MSGDirectory.BASE_PATCH_FMGS.items() if bnd == "item"
}


class ItemText:
    """Item names, summaries and descriptions from one `item.msgbnd.dcx`.

    Categories are named like "Accessory_name", "Accessory_description" (the short summary) and "Accessory_long_desc".
    """

    def __init__(self, bnd: MSGBND):
        self._bnd = bnd
        self._entries = {entry.entry_id: entry for entry in bnd.entries}
        self._fmgs = {entry_id: entry.to_binary_file(FMG) for entry_id, entry in self._entries.items()}
        self._changed: set[int] = set()

    @classmethod
    def from_path(cls, path: Path | str) -> ItemText:
        return cls(MSGBND.from_path(path))

    @classmethod
    def from_bytes(cls, data: bytes) -> ItemText:
        return cls(MSGBND.from_bytes(data))

    def _fmg_ids(self, category: str) -> list[int]:
        """Base FMG entry ID, followed by the patch entry ID if this binder has one."""
        base_id = CATEGORIES[category]
        patch_id = _PATCH_IDS.get(base_id)
        return [base_id] + ([patch_id] if patch_id in self._fmgs else [])

    def get(self, category: str, text_id: int) -> str | None:
        """The string the game displays: the patch string if non-empty, else the base string, else None."""
        for entry_id in reversed(self._fmg_ids(category)):
            if text := self._fmgs[entry_id].entries.get(text_id):
                return text
        return None

    def set(self, category: str, text_id: int, text: str) -> None:
        """Set the string in the base FMG and, if the category has one, the patch FMG."""
        for entry_id in self._fmg_ids(category):
            self._fmgs[entry_id].entries[text_id] = text
            self._changed.add(entry_id)

    @property
    def fmg_ids(self) -> list[int]:
        """Binder entry IDs of every FMG, base and patch (see `CATEGORIES` and `_PATCH_IDS`)."""
        return list(self._fmgs)

    def fmg_stem(self, fmg_id: int) -> str:
        return self._entries[fmg_id].stem

    def fmg_entries(self, fmg_id: int) -> dict[int, str]:
        """Copy of one FMG's strings, keyed by text ID."""
        return dict(self._fmgs[fmg_id].entries)

    def set_fmg_entries(self, fmg_id: int, entries: dict[int, str]) -> None:
        """Replace all strings of one FMG."""
        self._fmgs[fmg_id].entries = dict(entries)
        self._changed.add(fmg_id)

    def delete(self, category: str, text_id: int) -> None:
        """Remove the string from the base and patch FMGs."""
        for entry_id in self._fmg_ids(category):
            if self._fmgs[entry_id].entries.pop(text_id, None) is not None:
                self._changed.add(entry_id)

    def to_bytes(self) -> bytes:
        for entry_id in self._changed:
            self._entries[entry_id].set_uncompressed_data(bytes(self._fmgs[entry_id]))
        return bytes(self._bnd)

    def save(self, path: Path | str) -> None:
        for entry_id in self._changed:
            self._entries[entry_id].set_uncompressed_data(bytes(self._fmgs[entry_id]))
        self._bnd.write(path, force=True)
