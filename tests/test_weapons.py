"""Weapon randomizer (Phase 6.5). Uses the real install's game files with GameParam/item text redirected."""
import random
import statistics

import pytest

from ds1rand.features.weapons import (
    CLASS_SLOTS, CLASSES, DAMAGE, MAGIC_SCALING, MOVESET, NEGLIGIBLE, ON_HIT, PHYSICAL_SCALING, WHILE_HELD,
    WeaponConfig, WeaponTier, is_pinned, randomize_weapons,
)
from ds1rand.session import Session


@pytest.fixture
def session(redirected_install):
    return Session.open(redirected_install)


@pytest.fixture
def results(session):
    return randomize_weapons(session, WeaponConfig(), random.Random(1))


def test_pinned_weapons_untouched(session, results):
    weapons = session.base.params["EquipParamWeapon"]
    done = {r.weapon_id for r in results}
    pinned = [w for w in weapons.rows if is_pinned(w, weapons.row_values(w))]
    assert 900000 in pinned and pinned and not done & set(pinned)
    for weapon_id in pinned:
        assert session.store.values("EquipParamWeapon", weapon_id) == weapons.row_values(weapon_id)


def test_scaling_only_where_it_scales_damage(session, results):
    for r in results:
        new = session.store.values("EquipParamWeapon", r.weapon_id)
        total = sum(new[f] for f in DAMAGE) or 1
        if any(new[f] > 0 for f in MAGIC_SCALING) and any(f in r.changes for f in MAGIC_SCALING):
            assert new["attackBaseMagic"] / total > NEGLIGIBLE
        if any(new[f] > 0 for f in PHYSICAL_SCALING) and any(f in r.changes for f in PHYSICAL_SCALING):
            assert new["attackBasePhysics"] / total > NEGLIGIBLE


def test_rarer_tiers_are_worth_more(results):
    means = [statistics.mean(r.value for r in results if r.tier == t) for t in WeaponTier]
    assert means == sorted(means) and means[0] < 0.95 and means[-1] > 1.2


def test_starting_classes_can_use_their_weapons(session, results):
    chara = session.base.params["CharaInitParam"]
    for class_id in CLASSES:
        row = session.store.values("CharaInitParam", class_id)
        assert row == chara.row_values(class_id)
        for slot in CLASS_SLOTS:
            if row[slot] <= 0:
                continue
            weapon = session.store.values("EquipParamWeapon", row[slot] - row[slot] % 100)
            assert weapon["properStrength"] <= row["baseStr"] and weapon["properAgility"] <= row["baseDex"]
            assert weapon["properMagic"] <= row["baseMag"] and weapon["properFaith"] <= row["baseFai"]


def test_npcs_keep_vanilla_copies(session, results):
    chara = session.base.params["CharaInitParam"]
    weapons = session.base.params["EquipParamWeapon"]
    repointed = 0
    for row_id, values in session.store.changes().get("CharaInitParam", {}).items():
        before = chara.row_values(row_id)
        for slot in CLASS_SLOTS:
            if values[slot] != before[slot] and values[slot] > 0:
                copy = values[slot] - values[slot] % 100
                assert session.store.is_new("EquipParamWeapon", copy)
                assert values[slot] % 100 == before[slot] % 100  # upgrade level kept
                original = weapons.row_values(before[slot] - before[slot] % 100)
                assert session.store.values("EquipParamWeapon", copy) == original
                repointed += 1
    assert repointed > 20


def test_effects_are_new_rows_and_vanilla_effects_stay(session, results):
    weapons = session.base.params["EquipParamWeapon"]
    with_effects = [r for r in results if r.effects]
    assert with_effects
    for r in results:
        old, new = weapons.row_values(r.weapon_id), session.store.values("EquipParamWeapon", r.weapon_id)
        for name in ON_HIT + WHILE_HELD:
            if old[name] > 0:
                assert new[name] == old[name]
            elif new[name] > 0:
                assert session.store.is_new("SpEffectParam", new[name])
    texts = [t for r in with_effects for t in r.effects]
    assert any(t.startswith("While held:") for t in texts) and any("+" in t or "HP per hit" in t for t in texts)


def test_movesets_follow_family_and_type(session, results):
    weapons = session.base.params["EquipParamWeapon"]
    by_family = {}
    for r in results:
        family = r.weapon_id - r.weapon_id % 1000
        by_family.setdefault(family, set()).add(r.moveset_from)
        if r.moveset_from:
            mine, theirs = weapons.row_values(r.weapon_id), weapons.row_values(r.moveset_from)
            assert (mine["weaponCategory"], mine["wepmotionCategory"]) == \
                (theirs["weaponCategory"], theirs["wepmotionCategory"])
            new = session.store.values("EquipParamWeapon", r.weapon_id)
            assert all(new[f] == theirs[f] for f in MOVESET)
    assert all(len(v) == 1 for v in by_family.values())
    assert sum(1 for v in by_family.values() if None not in v) > 20


def test_descriptions(session, results):
    r = next(r for r in results if r.effects)
    text = session.text[("Weapon_long_desc", r.weapon_id)]
    assert f"Rarity: {r.tier.name.title()}" in text and r.effects[0] in text


def test_deterministic(redirected_install):
    def snapshot(seed):
        s = Session.open(redirected_install)
        return [(r.weapon_id, r.tier, r.changes, r.effects) for r in
                randomize_weapons(s, WeaponConfig(), random.Random(seed))]
    assert snapshot(4) == snapshot(4)
