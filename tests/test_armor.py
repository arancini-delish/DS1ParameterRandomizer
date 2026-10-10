"""Armor randomizer (Phase 6.6). Uses the real install's game files with GameParam/item text redirected."""
import random
import statistics

import pytest

from ds1rand.features.armor import RESIDENT, ArmorConfig, ArmorTier, is_pinned, randomize_armor
from ds1rand.session import Session

ARMOR_SLOTS = ("equip_Helm", "equip_Armer", "equip_Gaunt", "equip_Leg")


@pytest.fixture
def session(redirected_install):
    return Session.open(redirected_install)


@pytest.fixture
def results(session):
    return randomize_armor(session, ArmorConfig(), random.Random(1))


def test_pinned_rows_untouched(session, results):
    armor = session.base.params["EquipParamProtector"]
    names = session.base.text[12][1]
    pinned = {a for a in armor.rows if is_pinned(a, armor.row_values(a), names)}
    assert pinned and not pinned & {r.armor_id for r in results}
    for armor_id in pinned:
        assert session.store.values("EquipParamProtector", armor_id) == armor.row_values(armor_id)


def test_rarer_tiers_are_worth_more(results):
    means = [statistics.mean(r.value for r in results if r.tier == t) for t in ArmorTier]
    assert means == sorted(means) and means[0] < 0.9 and means[-1] > 1.25


def test_sets_share_their_tier(results):
    tiers = {}
    for r in results:
        tiers.setdefault(r.armor_id // 10000, set()).add(r.tier)
    assert all(len(t) == 1 for t in tiers.values())


def test_effects_go_into_free_slots(session, results):
    armor = session.base.params["EquipParamProtector"]
    with_effects = [r for r in results if r.effects]
    assert with_effects
    for r in results:
        old, new = armor.row_values(r.armor_id), session.store.values("EquipParamProtector", r.armor_id)
        for slot in RESIDENT:
            if old[slot] > 0:
                assert new[slot] == old[slot]
        added = [new[s] for s in RESIDENT if new[s] != old[s]]
        assert len(added) == (1 if r.effects else 0)
        assert all(session.store.is_new("SpEffectParam", s) for s in added)
    r = with_effects[0]
    text = session.text[("Armor_long_desc", r.armor_id)]
    assert text.startswith(f"Rarity: {r.tier.name.title()}\n{r.effects[0]}")


def test_npcs_keep_vanilla_copies(session, results):
    chara = session.base.params["CharaInitParam"]
    armor = session.base.params["EquipParamProtector"]
    repointed = 0
    for row_id, values in session.store.changes().get("CharaInitParam", {}).items():
        assert not 3000 <= row_id < 3010
        before = chara.row_values(row_id)
        for slot in ARMOR_SLOTS:
            if values[slot] != before[slot] and values[slot] > 0:
                copy = values[slot] - values[slot] % 100
                assert session.store.values("EquipParamProtector", copy) == \
                    armor.row_values(before[slot] - before[slot] % 100)
                repointed += 1
    assert repointed > 20


def test_deterministic(redirected_install):
    def snapshot(seed):
        s = Session.open(redirected_install)
        return [(r.armor_id, r.tier, r.changes, r.effects) for r in
                randomize_armor(s, ArmorConfig(), random.Random(seed))]
    assert snapshot(4) == snapshot(4)
