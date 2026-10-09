"""Feature usage of param rows (Phase 4a). Runs on the committed baseline and catalogue; no install needed."""
import pytest

from ds1rand.baseline.store import Baseline
from ds1rand.catalogue.usage import compute_usage, shared_rows
from ds1rand.graph.build import build_graph
from ds1rand.graph.model import Node


@pytest.fixture(scope="module")
def usage():
    baseline = Baseline.load()
    return compute_usage(build_graph(baseline), baseline)


def features(usage, param, row_id):
    return usage.get(Node.param(param, row_id), set())


def test_known_rows(usage):
    assert features(usage, "Magic", 3000) == {"player_spell"}  # Soul Arrow
    assert features(usage, "Magic", 13000) == {"enemy"}  # NPC caster copy of Soul Arrow
    # Both share the projectile: the coupling the allocator must break.
    assert features(usage, "Bullet", 3000) == {"player_spell", "enemy"}
    assert features(usage, "Bullet", 500) == {"player_weapon", "enemy"}  # Standard Arrow, also fired by NPCs
    assert features(usage, "SpEffectParam", 2000) == {"ring", "enemy"}  # Havel's Ring, also worn by NPC phantoms
    assert features(usage, "BehaviorParam", 5070) == {"environment"}  # trap fired from an event
    assert "engine" in features(usage, "SpEffectParam", 101)


def test_grants_do_not_count_as_usage(usage):
    assert not any(node.name in ("ItemLotParam", "ShopLineupParam", "EquipMtrlSetParam") for node in usage)
    # Events that check whether the player owns a spell item do not use the spell.
    assert not any(node.name == "Magic" and "environment" in f for node, f in usage.items())


def test_player_goods_stop_at_spells(usage):
    assert not any(node.name == "Magic" and "player_goods" in f for node, f in usage.items())


def test_shared_counts(usage):
    """Rows used by more than one feature, per param; a change means usage rules or the graph changed."""
    counts = {}
    for node in shared_rows(usage):
        counts[node.name] = counts.get(node.name, 0) + 1
    assert {p: counts.get(p, 0) for p in ("SpEffectParam", "Bullet", "AtkParam_Pc", "AtkParam_Npc", "Magic")} == {
        "SpEffectParam": 144, "Bullet": 80, "AtkParam_Pc": 703, "AtkParam_Npc": 7, "Magic": 0,
    }
