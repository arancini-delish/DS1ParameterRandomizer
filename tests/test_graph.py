"""Reference graph tests. These run on the committed baseline only; no game install needed."""
import pytest

from ds1rand.baseline.store import Baseline
from ds1rand.defs.meta import RefTarget, load_meta, parse_refs
from ds1rand.graph.model import Edge, Node, RefGraph
from ds1rand.graph.params import extract_param_edges, field_refs


@pytest.fixture(scope="module")
def baseline() -> Baseline:
    return Baseline.load()


@pytest.fixture(scope="module")
def graph(baseline) -> RefGraph:
    return extract_param_edges(baseline)


def refs(graph, node):
    return {(str(e.dst), e.field) for e in graph.refs_of(node)}


def test_parse_refs():
    assert parse_refs("AtkParam_Pc(refType=0),Bullet(refType=1),SpEffectParam") == (
        RefTarget("AtkParam_Pc", "refType", 0), RefTarget("Bullet", "refType", 1), RefTarget("SpEffectParam"),
    )


def test_meta_loads_every_file():
    meta = load_meta()
    assert len(meta) == 51
    assert meta["BulletParam"].fields["atkId_Bullet"].alt_name == "Attack ID"


def test_every_ref_target_is_a_real_param(baseline):
    for param, fields in field_refs(baseline).items():
        for field, targets in fields.items():
            assert all(t.param in baseline.params for t in targets), (param, field)


def test_every_edge_points_at_an_existing_row(baseline, graph):
    for edge in graph.edges:
        for node in (edge.src, edge.dst):
            assert node.id in baseline.params[node.name].rows, edge


def test_known_vanilla_references(graph):
    assert refs(graph, Node.param("Magic", 3000)) == {("Bullet:3000", "refId")}  # Soul Arrow
    assert ("SpEffectParam:2000", "refId") in refs(graph, Node.param("EquipParamAccessory", 100))  # Havel's Ring
    # Warrior's Longsword: CharaInitParam stores 201000 directly; the shield value carries an upgrade level.
    assert ("EquipParamWeapon:201000", "equip_Wep_Right") in refs(graph, Node.param("CharaInitParam", 3000))


def test_sharing_is_visible(graph):
    users = {str(e.src) for e in graph.users_of(Node.param("Bullet", 3000))}
    assert users == {"Magic:3000", "Magic:13000"}


def test_arrow_reaches_its_bullet_through_behaviors(graph):
    reached = graph.reach(Node.param("EquipParamWeapon", 2000000))  # Standard Arrow
    assert Node.param("Bullet", 500) in reached
    assert any(n.name == "BehaviorParam_PC" for n in reached)


def test_player_behaviors_only_reference_player_attacks(graph):
    for edge in graph.edges:
        if edge.src.name == "BehaviorParam_PC" and edge.dst.name.startswith("AtkParam"):
            assert edge.dst.name == "AtkParam_Pc"
        if edge.src.name == "BehaviorParam" and edge.dst.name.startswith("AtkParam"):
            assert edge.dst.name == "AtkParam_Npc"


def test_unresolved_references_are_known(graph):
    """Vanilla has a fixed set of dangling references; a change here means extraction rules changed."""
    assert len(graph.unresolved) == 308
    assert {u.reason for u in graph.unresolved} == {"missing row", "no behaviors with this variation"}


def test_write_load_round_trip(graph, tmp_path):
    path = tmp_path / "graph.json"
    graph.write(path)
    loaded = RefGraph.load(path)
    assert sorted(loaded.edges, key=repr) == sorted(graph.edges, key=repr)
    assert sorted(loaded.unresolved, key=repr) == sorted(graph.unresolved, key=repr)


def test_reach_and_reached_by():
    a, b, c = (Node.param("X", i) for i in (1, 2, 3))
    graph = RefGraph([Edge(a, b, "f", "test"), Edge(b, c, "f", "test", "inferred")])
    assert graph.reach(a) == {b, c}
    assert graph.reach(a, confidences=["certain"]) == {b}
    assert graph.reached_by(c) == {a, b}


def test_upgrade_paths_link_origins_to_upgraded_rows(graph):
    # Dagger -> its infusion paths (Crystal, Lightning, ...), which nothing else references.
    upgraded = {str(e.dst) for e in graph.refs_of(Node.param("EquipParamWeapon", 100000)) if e.field == "upgrade_path"}
    assert {"EquipParamWeapon:100100", "EquipParamWeapon:100200"} <= upgraded


def test_item_lot_chains_are_inferred(graph):
    edges = [e for e in graph.refs_of(Node.param("ItemLotParam", 2030)) if e.source == "item_lot_chain"]
    assert [(str(e.dst), e.confidence) for e in edges] == [("ItemLotParam:2031", "inferred")]
