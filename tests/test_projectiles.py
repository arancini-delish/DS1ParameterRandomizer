"""Projectile randomizer (Phase 6.3). Uses the real install's game files with GameParam/item text redirected to copies."""
import random

import pytest

from ds1rand.features.chains import CORRECTION_FIELDS, DAMAGE_FIELDS, chain_damage
from ds1rand.features.projectiles import (
    CARRY_LIMITS, THROWABLES, TIER_POWER, ProjectileConfig, find_slots, randomize_projectiles,
)
from ds1rand.session import Session


@pytest.fixture
def session(redirected_install):
    return Session.open(redirected_install)


def run(session, seed=1, **config):
    return randomize_projectiles(session, ProjectileConfig(**config), random.Random(seed))


def test_slots_cover_every_owner(session):
    slots = find_slots(session)
    kinds = {s.kind for s in slots}
    assert {"arrow", "great_arrow", "bolt", "throwable", "enemy", "trap"} <= kinds
    assert {s.row for s in slots if s.kind == "throwable"} == THROWABLES
    for s in slots:
        assert s.root in session.base.params["Bullet"].rows
        assert s.attack_param == ("AtkParam_Pc" if s.owner == "player" else "AtkParam_Npc")


def test_donors_keep_their_kind(session):
    results = run(session)
    slots = {(s.kind, s.root) for s in find_slots(session)}
    by_root = {}
    for kind, root in slots:
        by_root.setdefault(root, set()).add(kind)
    for r in results:
        if r.slot.kind == "enemy":
            group = {s.root for s in find_slots(session) if s.group == r.slot.group}
            assert r.donor in group
        else:
            assert r.slot.kind in by_root[r.donor]
        assert session.store.is_new("Bullet", r.root)
        assert session.store.values(r.slot.param, r.slot.row)["refId"] == r.root


def test_ammo_rows_firing_one_bullet_share_a_result(session):
    run(session)
    slots = find_slots(session)
    roots = {}
    for s in slots:
        if s.param == "BehaviorParam_PC":
            roots.setdefault((s.kind, s.root), set()).add(session.store.values(s.param, s.row)["refId"])
    assert all(len(new) == 1 for new in roots.values())
    assert any(len([s for s in slots if (s.kind, s.root) == key]) > 1 for key in roots)  # bolts share bullets


def test_throwables_carry_limit_and_summary(session):
    results = run(session)
    throwables = [r for r in results if r.slot.kind == "throwable"]
    assert len(throwables) == len(THROWABLES)
    for r in throwables:
        assert r.carry == CARRY_LIMITS[r.tier]
        assert session.store.values("EquipParamGoods", r.slot.row)["maxNum"] == r.carry
        assert session.text[("Item_description", r.slot.row)].startswith(r.tier.name.title())


def test_enemy_damage_follows_the_replaced_projectile(session):
    # No chains/status so the root attack carries the whole scaling.
    results = run(session, chain_chance=0, status_chance=0, motion_chance=0)
    checked = 0
    for r in results:
        if r.slot.owner == "player":
            continue
        own = chain_damage(session, r.slot.root, r.slot.attack_param)
        donor = chain_damage(session, r.donor, r.slot.attack_param)
        if not own or not donor:
            continue
        assert r.power == pytest.approx(TIER_POWER[r.tier] * own / donor, rel=1e-6)
        checked += 1
    assert checked > 50


def test_ammo_scales_corrections(session):
    results = run(session, chain_chance=0, status_chance=0, motion_chance=0)
    checked = 0
    for r in results:
        if r.slot.kind not in ("arrow", "great_arrow", "bolt"):
            continue
        donor_attack = session.base.params["Bullet"].row_values(r.donor)["atkId_Bullet"]
        if donor_attack <= 0 or donor_attack not in session.base.params["AtkParam_Pc"].rows:
            continue
        old = session.base.params["AtkParam_Pc"].row_values(donor_attack)
        new = session.store.values("AtkParam_Pc", session.store.values("Bullet", r.root)["atkId_Bullet"])
        if any(old[f] for f in DAMAGE_FIELDS):
            continue
        for f in CORRECTION_FIELDS:
            assert new[f] == round(old[f] * r.power)
        checked += 1
    assert checked


def test_owner_switches(session):
    results = run(session, enemy=False, environment=False)
    assert results and all(r.slot.owner == "player" for r in results)
    changed = session.store.changes().get("BehaviorParam", {})
    assert not changed


def test_deterministic(redirected_install):
    def snapshot(seed):
        s = Session.open(redirected_install)
        results = run(s, seed=seed, spell_effects=True)
        return [(r.slot.row, r.tier, r.donor, r.root, r.power, r.motion, r.chained_from, r.status) for r in results]
    assert snapshot(3) == snapshot(3)
    assert snapshot(3) != snapshot(4)
