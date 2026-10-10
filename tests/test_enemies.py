"""Enemy behaviour randomizer (Phase 6.4). Uses the real install's game files with GameParam/item text redirected."""
import random

import pytest

from ds1rand.features.enemies import (
    GROUPS, SENTINEL, TIER_RANGE, EnemyConfig, boss_entities, enemy_types, randomize_enemies,
)
from ds1rand.graph.model import Node
from ds1rand.session import Session


@pytest.fixture
def session(redirected_install):
    return Session.open(redirected_install)


def run(session, seed=1, **config):
    return randomize_enemies(session, EnemyConfig(**config), random.Random(seed))


def test_categories(session):
    assert len(boss_entities(session)) > 30
    types = enemy_types(session)
    categories = {t.category for t in types.values()}
    assert categories == {"regular", "boss", "human"}
    assert all(t.category in ("human", "boss") for t in types.values() if t.npc_id < 100000)
    regular = [t for t in types.values() if t.category == "regular"]
    assert sum(bool(t.think_rows) for t in regular) > 0.9 * len(regular)


def test_npc_moves_link_to_moveparam(session):
    edges = session.graph.refs_of(Node.param("NpcParam", 223000))
    assert any(e.field == "moveAnimId" and e.dst.name == "MoveParam" for e in edges)


def test_only_enabled_categories_change(session):
    results = run(session)
    types = enemy_types(session)
    assert results and all(r.category == "regular" for r in results)
    changed = set(session.store.changes().get("NpcParam", {}))
    assert not {t.npc_id for t in types.values() if t.category != "regular"} & changed


def test_factors_follow_tiers_and_fields_stay_in_range(session):
    results = run(session)
    npc = session.base.params["NpcParam"]
    for r in results:
        low, high = TIER_RANGE[r.tier]
        assert set(r.factors) == {*GROUPS, "speed"}
        assert all(low <= f <= high for f in r.factors.values())
        before, after = npc.row_values(r.npc_id), session.store.values("NpcParam", r.npc_id)
        if before["turnVellocity"] in (0, SENTINEL) or before["turnVellocity"] > SENTINEL:
            assert after["turnVellocity"] == before["turnVellocity"]
        if before["superArmorDurability"] <= 0:
            assert after["superArmorDurability"] == before["superArmorDurability"]
    think = session.base.params["NpcThinkParam"]
    for think_id in {t for r in results for t in r.think_rows}:
        before, after = think.row_values(think_id), session.store.values("NpcThinkParam", think_id)
        assert after["eye_angX"] <= 180 and after["ear_angX"] <= 90
        for name in ("nose_dist", "maxBackhomeDist"):
            if before[name] >= SENTINEL:
                assert after[name] == before[name]
        if before["backhomeBattleDist"] <= before["backhomeDist"] <= before["maxBackhomeDist"] < SENTINEL:
            assert after["backhomeBattleDist"] <= after["backhomeDist"] <= after["maxBackhomeDist"]


def test_speed_swaps_walk_and_run(session):
    results = run(session, tier_weights=(0.5, 0, 0, 0.5))
    moves = session.base.params["MoveParam"]
    swapped = [r for r in results if r.speed]
    assert {r.speed for r in swapped} == {"faster", "slower"}
    for r in swapped:
        before = session.base.params["NpcParam"].row_values(r.npc_id)["moveAnimId"]
        new = session.store.values("NpcParam", r.npc_id)["moveAnimId"]
        assert session.store.is_new("MoveParam", new)
        old_row, new_row = moves.row_values(before), session.store.values("MoveParam", new)
        if r.speed == "faster":
            assert new_row["walkF"] == old_row["dashF"] and new_row["dashF"] == old_row["dashF"]
        else:
            assert new_row["dashF"] == old_row["walkF"] and new_row["walkF"] == old_row["walkF"]


def test_disabled_groups_are_untouched(session):
    groups = dict.fromkeys((*GROUPS, "speed"), False) | {"turn": True}
    results = run(session, groups=groups)
    assert all(set(r.factors) == {"turn"} for r in results)
    changes = session.store.changes()
    assert "NpcThinkParam" not in changes and "MoveParam" not in changes
    npc = session.base.params["NpcParam"]
    for row_id, values in changes["NpcParam"].items():
        before = npc.row_values(row_id)
        assert {f for f in values if values[f] != before[f]} == {"turnVellocity"}


def test_deterministic(redirected_install):
    def snapshot(seed):
        s = Session.open(redirected_install)
        return [(r.npc_id, r.tier, r.factors, r.think_rows, r.speed) for r in run(s, seed=seed)]
    assert snapshot(2) == snapshot(2)
    assert snapshot(2) != snapshot(3)
