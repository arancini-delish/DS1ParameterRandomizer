"""Allocator, row store and writer (Phase 5). Allocation runs on the committed baseline; writing needs an install."""
import pytest

from ds1rand.alloc.allocator import allocate
from ds1rand.alloc.store import RowStore
from ds1rand.alloc.write import apply_params, write_output
from ds1rand.baseline.compare import FileState, check_gameparam
from ds1rand.baseline.store import Baseline
from ds1rand.catalogue.budget import RowBudget
from ds1rand.graph.build import build_graph
from ds1rand.graph.model import Node
from ds1rand.io.gameparam import GameParams

SPELL_PARAMS = {"Magic", "Bullet", "AtkParam_Pc", "SpEffectParam"}


@pytest.fixture(scope="module")
def baseline():
    return Baseline.load()


@pytest.fixture(scope="module")
def graph(baseline):
    return build_graph(baseline)


@pytest.fixture(scope="module")
def spells(graph, baseline):
    store = RowStore(baseline)
    return store, allocate(graph, baseline, store, ["player_spell"], params=SPELL_PARAMS)


def test_row_store(baseline):
    store = RowStore(baseline)
    store.add("Bullet", 9_000_000, copy_from=3000)
    store.set("Bullet", 9_000_000, {"life": 9.0})
    store.set("Bullet", 3010, dict(baseline.params["Bullet"].row_values(3010)))  # unchanged values
    assert store.changes() == {"Bullet": {9_000_000: {**baseline.params["Bullet"].row_values(3000), "life": 9.0}}}
    assert store.source_of("Bullet", 9_000_000) == 3000 and store.is_new("Bullet", 9_000_000)
    with pytest.raises(KeyError):
        store.set("Bullet", 3000, {"noSuchField": 1})


def test_spell_bullet_is_copied_for_player_spells_only(spells, baseline):
    store, allocation = spells
    new_bullet = store.values("Magic", 3000)["refId"]
    assert new_bullet != 3000 and 30000 <= new_bullet <= 32767  # Magic.refId is s16
    assert allocation.row_for(Node.param("Bullet", 3000), "player_spell") == new_bullet
    assert allocation.row_for(Node.param("Bullet", 3000), "enemy") == 3000
    assert store.values("Magic", 13000)["refId"] == 3000  # NPC caster copy keeps the original
    assert store.values("Bullet", 3000) == baseline.params["Bullet"].row_values(3000)


def test_copies_point_at_copies(spells):
    store, allocation = spells
    new_bullet = store.values("Magic", 3000)["refId"]
    new_attack = store.values("Bullet", new_bullet)["atkId_Bullet"]
    assert new_attack == allocation.row_for(Node.param("AtkParam_Pc", 10000), "player_spell") != 10000
    assert new_bullet in allocation.owned("player_spell")["Bullet"]


def test_allocation_is_deterministic(graph, baseline, spells):
    store = RowStore(baseline)
    allocate(graph, baseline, store, ["player_spell"], params=SPELL_PARAMS)
    assert store.changes() == spells[0].changes()


def test_reuse_only_cap(graph, baseline):
    store = RowStore(baseline)
    allocation = allocate(graph, baseline, store, ["player_spell"], RowBudget(default=0), params=SPELL_PARAMS)
    assert allocation.copies == {} and store.changes() == {}
    assert allocation.coupled("player_spell")[("Bullet", 3000)] == {"enemy"}


def test_partial_cap_keeps_the_cap(graph, baseline):
    store = RowStore(baseline)
    allocation = allocate(graph, baseline, store, ["player_spell"], RowBudget({"Bullet": 10}), params=SPELL_PARAMS)
    assert allocation.copies["Bullet"] == 10


def test_player_items_keep_their_ids_and_upgrade_offsets_survive(graph, baseline):
    store = RowStore(baseline)
    allocation = allocate(graph, baseline, store, ["enemy", "player_weapon"], params={"EquipParamWeapon"})
    # Player weapons are owned by ID (saves, item lots, shops): the player keeps the original, NPCs get copies.
    assert allocation.row_for(Node.param("EquipParamWeapon", 206000), "player_weapon") == 206000
    npc_copy = allocation.row_for(Node.param("EquipParamWeapon", 206000), "enemy")
    assert npc_copy >= 9_000_000 and npc_copy % 100 == 0
    assert store.values("CharaInitParam", 6000)["equip_Wep_Right"] == npc_copy + 3  # +3 weapon stays +3


def test_scope_limits_copies(graph, baseline):
    store = RowStore(baseline)
    allocation = allocate(graph, baseline, store, ["enemy"], params={"NpcParam", "NpcThinkParam", "MoveParam"})
    assert set(allocation.copies) <= {"NpcParam", "NpcThinkParam", "MoveParam"}


def test_write_on_vanilla_is_reported_as_ours(vanilla_gameparam, baseline, spells, tmp_path):
    store, _ = spells
    out = tmp_path / "GameParam.parambnd.dcx"
    data, patches = apply_params(vanilla_gameparam.read_bytes(), store)
    write_output(out, data, vanilla_gameparam.read_bytes(), patches)

    written = GameParams.from_path(out)
    new_bullet = written.row_values("Magic", 3000)["refId"]
    assert written.row_values("Bullet", new_bullet)["atkId_Bullet"] == store.values("Bullet", new_bullet)["atkId_Bullet"]
    _, report = check_gameparam(out, baseline)
    assert report.state is FileState.OURS
    assert {d.name for d in report.diffs} == set(store.changes())
