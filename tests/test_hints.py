"""Hint notes: parsing the item randomizer's output, and the Darksign description; pinned rings."""
import random
from pathlib import Path

import pytest

from ds1rand.features.hints import HINTED_ITEMS, DARKSIGN, LINE_WIDTH, add_hint_notes, item_regions, notes_text
from ds1rand.features.rings import RingConfig, randomize_rings
from ds1rand.graph.model import Node
from ds1rand.session import Session

HINTSHEET = "Hint Locations for Keys:\n\n" + "".join(f"{item}: Tomb of the Giants\n" for item in HINTED_ITEMS)


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


def test_notes_are_region_only_and_fit_the_description_box():
    text = notes_text({"Very Large Ember": "Painted World of Ariamis", "Key to Depths": "Anor Londo"})
    assert "(" not in text and "Key to Depths: Anor Londo" in text
    assert all(len(line) <= LINE_WIDTH for line in text.splitlines())


def test_hint_notes_go_into_the_darksign(install):
    session = Session.open(install)
    result = add_hint_notes(session)
    if result.problem:
        pytest.skip(f"the installed game has no matching item randomizer seed: {result.problem}")
    assert set(result.hints) == set(HINTED_ITEMS) and result.goods_id == DARKSIGN
    text = session.text[("Item_long_desc", DARKSIGN)]
    assert all(f"{item}: " in text.replace("\n  ", " ") for item in HINTED_ITEMS)
    assert not session.store.changes()  # no params touched: only the text


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
