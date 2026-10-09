"""Decoupling costs, row budgets and new row IDs (Phase 4c). Runs on the committed baseline; no install needed."""
import pytest

from ds1rand.baseline.store import Baseline
from ds1rand.catalogue.budget import (
    IdAllocator, RowBudget, decoupling, param_budgets, reference_limits, unit_footprint,
)
from ds1rand.graph.build import build_graph
from ds1rand.graph.model import Node


@pytest.fixture(scope="module")
def baseline():
    return Baseline.load()


@pytest.fixture(scope="module")
def graph(baseline):
    return build_graph(baseline)


@pytest.fixture(scope="module")
def groups(graph, baseline):
    return decoupling(graph, baseline)


@pytest.fixture(scope="module")
def budgets(graph, baseline):
    return param_budgets(graph, baseline)


def as_sets(row_groups):
    return {frozenset(g) for g in row_groups.groups}


def test_spell_bullet_shared_with_npc_casters_can_be_split(groups):
    soul_arrow = groups[Node.param("Bullet", 3000)]
    assert as_sets(soul_arrow) == {frozenset({"player_spell"}), frozenset({"enemy"})}
    assert soul_arrow.copies_needed == 1 and not soul_arrow.coupled


def test_ammo_shared_through_behavior_variation_stays_coupled(groups):
    # NPC archers reach the Standard Arrow bullet through the weapon's behavior variation, an engine-computed ID.
    arrow = groups[Node.param("Bullet", 500)]
    assert as_sets(arrow) == {frozenset({"player_weapon", "enemy"})}
    assert arrow.copies_needed == 0 and arrow.coupled


def test_param_budgets(budgets):
    summary = {p: (b.used, b.copies_needed, b.coupled_rows) for p, b in budgets.items()}
    assert summary["Bullet"] == (514, 72, 8)
    assert summary["SpEffectParam"] == (486, 113, 43)
    assert summary["Magic"] == (104, 0, 0)
    assert summary["BehaviorParam_PC"] == (3143, 0, 1153)


def test_unit_footprints(graph):
    assert unit_footprint(graph, Node.param("Magic", 3000)) == {"Magic": 1, "Bullet": 1, "AtkParam_Pc": 1}
    assert unit_footprint(graph, Node.param("Magic", 5500)) == {"Magic": 1, "Bullet": 6, "AtkParam_Pc": 6}


def test_row_budget_caps(budgets):
    assert RowBudget().plan(budgets)["Bullet"] == {"decoupling": 72, "cap": None, "surplus": None, "shortfall": 0}
    assert RowBudget(default=0).plan(budgets)["Bullet"]["shortfall"] == 72  # reuse only
    assert RowBudget({"Bullet": 100}).plan(budgets)["Bullet"]["surplus"] == 28


def test_spell_roots_must_fit_s16(baseline):
    limits = reference_limits(baseline)
    assert limits["Bullet"][("Magic", "refId")] == 32767
    assert limits["SpEffectParam"][("ReinforceParamWeapon", "spEffectId1")] == 255


def test_id_allocator(baseline):
    allocator = IdAllocator(baseline)
    narrow = allocator.allocate("Bullet", max_id=32767)
    assert 30000 <= narrow <= 32767 and narrow not in baseline.params["Bullet"].rows
    assert allocator.allocate("Bullet") >= 9_000_000  # unconstrained rows use the wide block
    assert allocator.allocate("Bullet", max_id=32767) != narrow
    with pytest.raises(ValueError):
        allocator.allocate("SpEffectParam", max_id=255)
