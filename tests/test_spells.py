"""Spell randomizer (Phase 6.2). Uses the real install's game files with GameParam/item text redirected to copies."""
import random

import pytest

from ds1rand.catalogue.subtypes import CAST_ANIMATIONS, bullet_chain
from ds1rand.features.spells import DEFAULT_PINNED, POWER_LIMITS, SpellConfig, randomize_spells, usage_power
from ds1rand.io.gameparam import GameParams
from ds1rand.session import Session


@pytest.fixture
def session(redirected_install):
    return Session.open(redirected_install)


def run(session, seed=1, **config):
    return randomize_spells(session, SpellConfig(**config), random.Random(seed))


def test_usage_curve():
    assert usage_power(30, False) == 0.5 and usage_power(1, False) == 3.0
    assert usage_power(8, False) > usage_power(12, False) > usage_power(30, False)
    assert usage_power(80, True) == 1.0


def test_spells_keep_school_and_cast_family(session):
    results = run(session)
    magic = session.base.params["Magic"]
    for r in results:
        before, after = magic.row_values(r.magic_id), session.store.values("Magic", r.magic_id)
        assert after["ezStateBehaviorType"] == before["ezStateBehaviorType"]
        old, new = CAST_ANIMATIONS[before["refType"]], CAST_ANIMATIONS[after["refType"]]
        assert old == new or {old, new} == {"projectile", "projectile_charged"}
        assert after["refCategory"] == before["refCategory"]


def test_pinned_spells_untouched(session):
    run(session)
    changed = set(session.store.changes().get("Magic", {}))
    assert not changed & DEFAULT_PINNED
    assert 5210 not in changed  # Homeward


def test_payload_is_new_rows_with_scaled_damage(session):
    results = run(session)
    bullets = [r for r in results if session.store.values("Magic", r.magic_id)["refCategory"] == 1]
    assert bullets
    for r in bullets:
        assert r.root <= 32767 and session.store.is_new("Bullet", r.root)  # Magic.refId is s16
        assert POWER_LIMITS[0] <= r.power <= POWER_LIMITS[1]
        donor_root = session.base.params["Magic"].row_values(r.donor)["refId"]
        donor_attack = session.base.params["Bullet"].row_values(donor_root)["atkId_Bullet"]
        new_attack = session.store.values("Bullet", r.root)["atkId_Bullet"]
        if donor_attack > 0 and donor_attack in session.base.params["AtkParam_Pc"].rows:
            assert session.store.is_new("AtkParam_Pc", new_attack)
            old = session.base.params["AtkParam_Pc"].row_values(donor_attack)
            new = session.store.values("AtkParam_Pc", new_attack)
            for f in ("atkMag", "atkFire", "atkThun", "atkPhys"):
                assert new[f] == round(old[f] * r.power)


def test_chains_are_copied_and_relinked(session):
    results = run(session)
    for r in results:
        if session.store.values("Magic", r.magic_id)["refCategory"] != 1:
            continue
        donor_chain = bullet_chain(session.base, session.base.params["Magic"].row_values(r.donor)["refId"])
        node, seen = r.root, []
        while node > 0 and node not in seen and session.store.exists("Bullet", node):
            seen.append(node)
            node = session.store.values("Bullet", node)["HitBulletID"]
        extra = len(bullet_chain(session.base, r.chained_from[1])[:6]) if r.chained_from else 0
        assert len(seen) == len(donor_chain) + extra and all(session.store.is_new("Bullet", b) for b in seen)


def test_npc_spells_have_no_costs(session):
    results = run(session)
    npc = [r for r in results if r.owner == "enemy"]
    assert npc and all(r.magic_id >= 10000 for r in npc)
    for r in npc:
        assert session.store.values("Magic", r.magic_id)["maxQuantity"] == \
            session.base.params["Magic"].row_values(r.magic_id)["maxQuantity"]


def test_same_seed_same_spells(redirected_install):
    first = run(Session.open(redirected_install))
    second = run(Session.open(redirected_install))
    assert [(r.magic_id, r.donor, r.casts, r.power) for r in first] == \
        [(r.magic_id, r.donor, r.casts, r.power) for r in second]


def test_options(session):
    results = run(session, enemy=False, visual_chance=0, status_chance=0)
    assert all(r.owner == "player" and r.visual_from is None and r.status is None for r in results)


def test_write_and_read_back(redirected_install):
    session = Session.open(redirected_install)
    results = run(session)
    session.write({"seed": 1})
    params = GameParams.from_path(redirected_install.gameparam)
    for r in results:
        assert params.row_values("Magic", r.magic_id)["refId"] == r.root


def chain_of(session, root):
    node, seen = root, []
    while node > 0 and node not in seen and session.store.exists("Bullet", node):
        seen.append(node)
        node = session.store.values("Bullet", node)["HitBulletID"]
    return seen


def test_visual_pool_spans_schools(redirected_install):
    from ds1rand.features.spells import _SpellBuilder

    builder = _SpellBuilder(Session.open(redirected_install), SpellConfig(), random.Random(0))
    schools = {builder.vanilla[m]["ezStateBehaviorType"] for m, _ in builder.visual_pool}
    assert schools == {0, 1, 2} and len(builder.visual_pool) > 40


def test_motion_changes_only_moving_bullets(session):
    from ds1rand.catalogue.subtypes import classify_bullet

    results = run(session, motion_chance=1.0, chain_chance=0, visual_chance=0)
    changed = [r for r in results if r.motion]
    assert changed
    for r in changed:
        donor_root = session.base.params["Magic"].row_values(r.donor)["refId"]
        motion = classify_bullet(session.base.params["Bullet"].row_values(donor_root)).motion
        assert motion in ("linear", "homing", "lobbed")


def test_chained_effects_extend_the_chain(session):
    results = run(session, chain_chance=1.0, motion_chance=0, visual_chance=0, status_chance=0)
    chained = [r for r in results if r.chained_from]
    assert chained
    for r in chained:
        donor_chain = bullet_chain(session.base, session.base.params["Magic"].row_values(r.donor)["refId"])
        child_chain = bullet_chain(session.base, r.chained_from[1])[:6]
        assert len(chain_of(session, r.root)) == len(donor_chain) + len(child_chain)


def test_chained_child_damage_is_scaled(session):
    from ds1rand.features.spells import CHILD_POWER

    results = run(session, chain_chance=1.0, motion_chance=0, visual_chance=0, status_chance=0)
    checked = 0
    for r in [r for r in results if r.chained_from]:
        child = bullet_chain(session.base, r.chained_from[1])[0]
        attack = session.base.params["Bullet"].row_values(child)["atkId_Bullet"]
        if attack <= 0 or attack not in session.base.params["AtkParam_Pc"].rows:
            continue
        donor_length = len(bullet_chain(session.base, session.base.params["Magic"].row_values(r.donor)["refId"]))
        copied = chain_of(session, r.root)[donor_length]
        old = session.base.params["AtkParam_Pc"].row_values(attack)
        new = session.store.values("AtkParam_Pc", session.store.values("Bullet", copied)["atkId_Bullet"])
        assert 0 < r.child_power <= POWER_LIMITS[1] * CHILD_POWER
        for f in ("atkMag", "atkFire", "atkThun", "atkPhys"):
            assert new[f] == round(old[f] * r.child_power)
        checked += 1
    assert checked
