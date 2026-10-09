from ds1rand.graph.diff import diff_edges, summarise_edges, usage_changes
from ds1rand.graph.model import Edge, Node, RefGraph

MAGIC, OLD, NEW = Node.param("Magic", 3000), Node.param("Bullet", 3000), Node.param("Bullet", 30000)


def test_diff_edges_ignores_source_and_confidence():
    old = RefGraph([Edge(MAGIC, OLD, "refId", "meta"), Edge(OLD, Node.param("AtkParam_Pc", 1), "atkId_Bullet", "meta")])
    new = RefGraph([Edge(MAGIC, NEW, "refId", "meta"),
                    Edge(OLD, Node.param("AtkParam_Pc", 1), "atkId_Bullet", "soulstruct", "ambiguous")])
    added, removed = diff_edges(old, new)
    assert [(str(e.src), str(e.dst)) for e in added] == [("Magic:3000", "Bullet:30000")]
    assert [(str(e.src), str(e.dst)) for e in removed] == [("Magic:3000", "Bullet:3000")]
    assert summarise_edges(added) == {("Magic", "refId", "Bullet"): 1}


def test_usage_changes():
    old = {OLD: {"player_spell", "enemy"}, MAGIC: {"player_spell"}}
    new = {OLD: {"enemy"}, NEW: {"player_spell"}, MAGIC: {"player_spell"}}
    assert usage_changes(old, new) == {
        OLD: (frozenset({"player_spell", "enemy"}), frozenset({"enemy"})),
        NEW: (frozenset(), frozenset({"player_spell"})),
    }
