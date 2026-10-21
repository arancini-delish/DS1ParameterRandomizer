"""Hint item: parsing the item / fog gate randomizer output, and the item itself."""
import random
from pathlib import Path

import pytest

from ds1rand.features.hints import (
    CLASSES, HINTED_ITEMS, add_hint_item, fog_entrances, item_regions, region_of,
)
from ds1rand.features.rings import RingConfig, randomize_rings
from ds1rand.graph.model import Node
from ds1rand.session import Session

HINTSHEET = """Hint Locations for Keys:

Covenant of Artorias: Tomb of the Giants
Key to the Seal: Oolacile Township
Peculiar Doll: Chasm of the Abyss
Broken Pendant: The Duke's Archives
Orange Charred Ring: Anor Londo
Darkmoon Seance Ring: Great Hollow
"""
FOG_LOG = """Seed: 1. Options: boss
asylum (scaling: 100%)
  From asylum_balcony (in map) to asylum
darkroot (scaling: 100%)
  From parish_church (To Sif) to darkroot
totg (scaling: 120%)
  From totg_lower (in map) to totg
  From darkroot (Down the well) to totg
"""


def _seed(root: Path, name: str, lots: bytes) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "ItemLotParam.param").write_bytes(lots)
    (folder / "hintsheet.txt").write_text(HINTSHEET, encoding="utf-8")


def test_item_regions_use_the_seed_matching_the_installed_lots(tmp_path):
    _seed(tmp_path, "random-seed-2026-10-12--20-00-00-000000", b"installed")
    _seed(tmp_path, "random-seed-2026-10-13--20-00-00-000000", b"newer but not installed")
    seed_dir, regions = item_regions(tmp_path, b"installed")
    assert seed_dir.name == "random-seed-2026-10-12--20-00-00-000000"
    assert regions["Covenant of Artorias"] == "Tomb of the Giants" and set(HINTED_ITEMS) <= set(regions)
    assert item_regions(tmp_path, b"other") == (None, {})


def test_fog_entrances(tmp_path):
    runs = tmp_path / "FogMod_v0.3" / "runs"
    runs.mkdir(parents=True)
    (runs / "2026-10-12_20.50.55_log_1_1.txt").write_text(FOG_LOG, encoding="utf-8")
    log, entrances = fog_entrances(tmp_path)
    assert log.name.endswith("_log_1_1.txt")
    assert entrances["Tomb of the Giants"] == "Darkroot Garden, Down the well"
    assert entrances["Darkroot Garden"] == "Undead Parish, To Sif"
    assert region_of("demonruins_izalithlava") == "Lost Izalith" and region_of("demonruins_lava") == "Demon Ruins"


def test_hint_item_in_every_starting_inventory(install, tmp_path):
    session = Session.open(install)
    result = add_hint_item(session)
    if result.problem:
        pytest.skip(f"the installed game has no matching item randomizer seed: {result.problem}")
    assert set(result.hints) == set(HINTED_ITEMS)
    goods = session.store.values("EquipParamGoods", result.goods_id)
    assert session.store.is_new("EquipParamGoods", result.goods_id) and goods["refCategory"] == 0
    for class_id in CLASSES:
        row = session.store.values("CharaInitParam", class_id)
        assert result.goods_id in [row[f"item_{i:02d}"] for i in range(1, 11)]
    text = session.text[("Item_long_desc", result.goods_id)]
    assert all(len(line) <= 44 for line in text.splitlines()) and "Covenant of Artorias" in text


def test_pinned_and_event_checked_rings_keep_their_speffects(redirected_install):
    session = Session.open(redirected_install)
    rings = session.base.params["EquipParamAccessory"]
    randomize_rings(session, RingConfig(), random.Random(1))
    changes = session.store.changes()
    for ring in RingConfig().pinned:  # e.g. Covenant of Artorias: New Londo's events check its SpEffect 2200
        speffect = rings.row_values(ring)["refId"]
        assert session.store.values("EquipParamAccessory", ring)["refId"] == speffect
        assert speffect not in changes.get("SpEffectParam", {})
    for ring in rings.rows:
        speffect = rings.row_values(ring)["refId"]
        users = {e.src.kind for e in session.graph.users_of(Node.param("SpEffectParam", speffect))}
        if ring and "emevd" in users:
            assert session.store.values("EquipParamAccessory", ring)["refId"] == speffect
