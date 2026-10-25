"""Hint notes: the Master Key's description tells in which region each key item is this seed.

Where the items are comes from the item randomizer's own output in the game folder: each run writes
`random-seed-<time>/hintsheet.txt` (region of every key item) next to the `ItemLotParam.param` it installed. The
newest seed folder whose `ItemLotParam.param` is byte-identical to the item lots in the installed params (the base
ds1rand builds on) is used, so hints never come from an older run.

The notes go into the Master Key's long description (the Thief starts with it, any class can pick it as a gift).
Adding a new item to the starting classes was tried first (a new EquipParamGoods row in CharaInitParam 3000-3009
item slots): the output was right, but the game did not give the item at character creation, so an existing item
carries the notes instead.
"""
from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from ds1rand.io.gameparam import RawGameParam
from ds1rand.session import Session

HINTED_ITEMS = ("Covenant of Artorias", "Key to the Seal", "Peculiar Doll", "Broken Pendant", "Orange Charred Ring",
                "Darkmoon Seance Ring", "Key to Depths", "Large Ember", "Very Large Ember")
MASTER_KEY = 2100
LINE_WIDTH = 44  # item descriptions do not wrap by themselves
HEADER = "Notes scratched into the key's leather tag:"


@dataclass
class HintResult:
    goods_id: int = 0  # the item carrying the notes
    seed_dir: Path | None = None
    hints: dict[str, str] = field(default_factory=dict)  # item -> region
    problem: str = ""  # why no notes were written


def item_regions(root: Path, item_lots: bytes) -> tuple[Path | None, dict[str, str]]:
    """The newest item randomizer seed folder matching the installed item lots, and its key item regions."""
    for seed_dir in sorted(Path(root).glob("random-seed-*"), reverse=True):
        lots, sheet = seed_dir / "ItemLotParam.param", seed_dir / "hintsheet.txt"
        if lots.is_file() and sheet.is_file() and lots.read_bytes() == item_lots:
            regions = {}
            for line in sheet.read_text(encoding="utf-8", errors="replace").splitlines():
                item, sep, region = line.partition(": ")
                if sep and region.strip():
                    regions[item.strip()] = region.strip()
            return seed_dir, regions
    return None, {}


def notes_text(hints: dict[str, str]) -> str:
    lines = textwrap.wrap(HEADER, LINE_WIDTH) + [""]
    for item, region in hints.items():
        lines += textwrap.wrap(f"{item}: {region}", LINE_WIDTH, subsequent_indent="  ")
    return "\n".join(lines)


def add_hint_notes(session: Session) -> HintResult:
    result = HintResult()
    item_lots = RawGameParam.from_bytes(session.gameparam_base.data).param_bytes("ItemLotParam")
    result.seed_dir, regions = item_regions(session.install.root, item_lots)
    if result.seed_dir is None:
        result.problem = "no item randomizer seed folder (random-seed-*) matches the installed item lots"
        return result
    result.hints = {item: regions[item] for item in HINTED_ITEMS if item in regions}
    result.goods_id = MASTER_KEY
    session.text[("Item_long_desc", MASTER_KEY)] = notes_text(result.hints)
    return result
