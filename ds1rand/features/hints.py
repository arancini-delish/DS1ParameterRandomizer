"""Hint item: a key item in every starting inventory whose description tells where the key items are this seed.

Where the items are comes from the item randomizer's own output in the game folder: each run writes
`random-seed-<time>/hintsheet.txt` (region of every key item) next to the `ItemLotParam.param` it installed. The
newest seed folder whose `ItemLotParam.param` is byte-identical to the item lots in the installed params (the base
ds1rand builds on) is used, so hints never come from an older run. If the fog gate randomizer ran too, its newest run
log (`FogMod_v0.3/runs/*_log_*.txt`) adds how each region is entered this seed: the first connection into the region in
the log's route order, e.g. "Undead Parish, To Gargoyles".

The item is a new EquipParamGoods row (a copy of the Peculiar Doll: an inert key item that is never used up) given to
every starting class. Giving it on resting at the first bonfire would need event script edits; the starting inventory
gets it into the player's hands at the same point without touching events.
"""
from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from ds1rand.io.gameparam import RawGameParam
from ds1rand.session import Session

HINTED_ITEMS = ("Covenant of Artorias", "Key to the Seal", "Peculiar Doll", "Broken Pendant", "Orange Charred Ring",
                "Darkmoon Seance Ring")
TEMPLATE_GOODS = 384  # Peculiar Doll: key item, no effect, not consumed
ICON = 2007  # Servant Roster's book icon
CLASSES = range(3000, 3010)
ITEM_SLOTS = 10
NAME = "Wanderer's Notes"
SUMMARY = "Notes on where key items lie"
LINE_WIDTH = 44  # item descriptions do not wrap by themselves
GOODS_ID_MAX = 32767  # stay in the narrow new-ID block: goods IDs are shown and stored widely

# Item randomizer region -> fog gate randomizer area-ID prefixes (longest match wins).
REGION_AREAS: dict[str, tuple[str, ...]] = {
    "Undead Asylum": ("asylum",),
    "Firelink Shrine": ("firelink",),
    "Undead Burg": ("burg",),
    "Lower Undead Burg": ("burg_lower", "burg_capra"),
    "Undead Parish": ("parish",),
    "Depths": ("depths",),
    "Blighttown": ("blighttown",),
    "Great Hollow": ("greathollow",),
    "Ash Lake": ("greathollow_ashlake",),
    "Darkroot Garden": ("darkroot",),
    "Darkroot Basin": ("darkroot",),
    "Catacombs": ("catacombs",),
    "Tomb of the Giants": ("totg",),
    "New Londo Ruins": ("newlondo",),
    "After defeating the Four Kings": ("newlondo_fourkings",),
    "Sen's Fortress": ("sens",),
    "Anor Londo": ("anorlondo",),
    "Painted World of Ariamis": ("paintedworld",),
    "Demon Ruins": ("demonruins",),
    "Lost Izalith": ("demonruins_izalith", "demonruins_bedofchaos"),
    "The Duke's Archives": ("dukes",),
    "Crystal Cave": ("dukes_caves", "dukes_seath2"),
    "Kiln of the First Flame": ("kiln",),
    "Royal Wood": ("dlc_forest", "dlc_artorias", "dlc_kalameet"),
    "Oolacile Township": ("dlc_township",),
    "Oolacile Sanctuary": ("dlc_sanctuary",),
    "Chasm of the Abyss": ("dlc_manus", "dlc_bottom"),
}


@dataclass
class HintResult:
    goods_id: int = 0
    seed_dir: Path | None = None
    fog_log: Path | None = None
    hints: dict[str, str] = field(default_factory=dict)  # item -> hint line
    problem: str = ""  # why no hint item was added


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


def fog_entrances(root: Path) -> tuple[Path | None, dict[str, str]]:
    """Region -> how it is entered, from the newest fog gate randomizer log ("<from region>, <entrance>")."""
    logs = sorted(Path(root).glob("FogMod*/runs/*_log_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not logs:
        return None, {}
    route: list[tuple[str, str, str]] = []  # (area, from area, description), in the log's route order
    area = None
    for line in logs[0].read_text(encoding="utf-8", errors="replace").splitlines():
        if match := re.match(r"^([a-z0-9_]+) \(scaling", line):
            area = match.group(1)
        elif area and (match := re.match(r"^\s+From ([a-z0-9_]+) \((.*?)\) to ", line)):
            route.append((area, match.group(1), match.group(2)))
    entrances = {}
    for region in REGION_AREAS:
        for area, source, description in route:
            if region_of(area) == region and region_of(source) != region and description != "in map":
                entrances[region] = f"{region_of(source) or source}, {description}"
                break
    return logs[0], entrances


def region_of(area: str) -> str | None:
    best, length = None, -1
    for region, prefixes in REGION_AREAS.items():
        for prefix in prefixes:
            if area.startswith(prefix) and len(prefix) > length:
                best, length = region, len(prefix)
    return best


def add_hint_item(session: Session) -> HintResult:
    result = HintResult()
    root = session.install.root
    item_lots = RawGameParam.from_bytes(session.gameparam_base.data).param_bytes("ItemLotParam")
    result.seed_dir, regions = item_regions(root, item_lots)
    if result.seed_dir is None:
        result.problem = "no item randomizer seed folder (random-seed-*) matches the installed item lots"
        return result
    result.fog_log, entrances = fog_entrances(root)
    for item in HINTED_ITEMS:
        region = regions.get(item)
        if region is None:
            continue
        way_in = entrances.get(region)
        result.hints[item] = f"{item}: {region}" + (f" (way in: {way_in})" if way_in else "")

    goods_id = session.ids.allocate("EquipParamGoods", GOODS_ID_MAX)
    session.store.add("EquipParamGoods", goods_id, copy_from=TEMPLATE_GOODS)
    session.store.set("EquipParamGoods", goods_id, {"iconId": ICON})
    result.goods_id = goods_id
    session.text[("Item_name", goods_id)] = NAME
    session.text[("Item_description", goods_id)] = SUMMARY
    lines = textwrap.wrap("Notes left by a wanderer who walked this world before.", LINE_WIDTH) + [""]
    for hint in list(result.hints.values()) or ["The pages are blank."]:
        lines += textwrap.wrap(hint, LINE_WIDTH, subsequent_indent="  ")
    session.text[("Item_long_desc", goods_id)] = "\n".join(lines)

    chara = session.base.params["CharaInitParam"]
    for class_id in CLASSES:
        if class_id not in chara.rows:
            continue
        row = session.store.values("CharaInitParam", class_id)
        slot = next((i for i in range(1, ITEM_SLOTS + 1) if row[f"item_{i:02d}"] <= 0), None)
        if slot is not None:
            session.store.set("CharaInitParam", class_id, {f"item_{slot:02d}": goods_id, f"itemNum_{slot:02d}": 1})
    return result
