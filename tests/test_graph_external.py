"""Graph edges from EMEVD and MSB. The committed `data/catalogue` files are tested without an install; re-extraction is
compared against them when a vanilla install is available."""
import pytest

from ds1rand.baseline.store import Baseline
from ds1rand.graph.build import CATALOGUE_DIR, EXTERNAL_SOURCES, build_graph
from ds1rand.graph.model import Node, RefGraph


@pytest.fixture(scope="module")
def baseline() -> Baseline:
    return Baseline.load()


@pytest.fixture(scope="module")
def graph(baseline) -> RefGraph:
    return build_graph(baseline)


def users(graph, node):
    return {(str(e.src), e.field) for e in graph.users_of(node)}


def test_external_edges_point_at_existing_rows(baseline):
    for file_name in EXTERNAL_SOURCES:
        external = RefGraph.load(CATALOGUE_DIR / file_name)
        assert external.edges
        for edge in external.edges:
            if edge.dst.kind == "param":
                assert edge.dst.id in baseline.params[edge.dst.name].rows, edge


def test_unresolved_counts(graph):
    """Vanilla dangling references per source; a change here means extraction rules changed."""
    counts = {}
    for u in graph.unresolved:
        counts[u.src.kind] = counts.get(u.src.kind, 0) + 1
    assert counts == {"param": 377, "emevd": 3, "msb": 136, "tae": 95, "lua": 2}


def test_event_only_behaviors(graph):
    # Trap/hazard behaviors that no param references, only event scripts.
    assert users(graph, Node.param("BehaviorParam", 5070)) == {
        ("emevd/m15_00_00_00:11505260", "ShootProjectile.behavior_id"),
        ("emevd/m15_00_00_00:11505270", "ShootProjectile.behavior_id"),
    }
    assert ("BehaviorParam:5000", "CreateHazard.behavior_param_id") in {
        (str(e.dst), e.field) for e in graph.refs_of(Node("emevd", "m10_01_00_00", 11010008))
    }


def test_event_arguments_are_substituted(graph):
    # KillBoss in a templated event resolves to the boss area through RunEvent arguments.
    assert ("emevd/m10_01_00_00:11010001", "KillBoss.game_area_param_id") in users(
        graph, Node.param("GameAreaParam", 1010800)
    )


def test_map_entries(graph):
    assert ("msb/m15_01_00_00/c0000_0003:6010", "character_id") in users(graph, Node.param("NpcParam", 6010))
    # Treasures sharing a name get distinct nodes.
    assert ("msb/m10_00_00_00/takara#11:-1", "item_lot_1") in users(graph, Node.param("ItemLotParam", 1000120))
    character_models = {e.dst.name for e in graph.edges if e.src.kind == "msb" and e.dst.kind == "model"}
    assert "c0000" in character_models and len(character_models) > 50


def test_re_extraction_matches_committed(install, baseline, tmp_path):
    """Re-extract from the same files recorded in `sources.json` (live or `.bak`); skip if those are not available."""
    import json

    from ds1rand.graph.build import SOURCES_FILE, extract_external, source_files, source_hashes

    recorded = json.loads((CATALOGUE_DIR / SOURCES_FILE).read_text(encoding="utf-8"))
    prefer_bak = any(entry["file"].endswith(".bak") for files in recorded.values() for entry in files.values())
    if source_hashes(source_files(install, prefer_bak)) != recorded:
        pytest.skip("Install does not have the recorded vanilla source files")
    extract_external(install, baseline, tmp_path, prefer_bak)
    for file_name in [*EXTERNAL_SOURCES, SOURCES_FILE]:
        assert (tmp_path / file_name).read_text(encoding="utf-8") == (CATALOGUE_DIR / file_name).read_text(
            encoding="utf-8"
        ), file_name


def test_tae_common_behaviors_reach_rows_outside_the_id_formula(graph):
    # Rat (c1200) animations invoke behavior rows directly; these do not follow 200000000 + variation * 1000 + judge.
    assert ("tae/c1200:701", "InvokeCommonBehavior.row") in users(graph, Node.param("BehaviorParam", 20108))


def test_placed_enemy_reaches_its_bullets_through_animations(graph):
    # Stray Demon: MSB placement -> model -> animation -> behavior (by judge ID) -> bullet.
    placement = Node("msb", "m18_01_00_00/c2230_0000", 1810810)
    assert Node("model", "c2230", 0) in graph.reach(placement)
    assert ("tae/c2230:3006", "InvokeBulletBehavior.judge") in users(graph, Node.param("BehaviorParam", 222300160))
    assert {n for n in graph.reach(placement) if n.kind == "param" and n.name == "Bullet"}


def test_player_animations_add_speffects(graph):
    assert ("tae/c0000:1500", "AddSpEffect66.row") in users(graph, Node.param("SpEffectParam", 32))


def test_no_inferred_behavior_variation_fallback(graph):
    # TAE shows severed parts (tails, heads) invoke no behaviors, so their variations are not linked to their body's.
    assert not [e for e in graph.edges if e.source == "behavior_variation" and e.confidence != "certain"]


def test_ai_goals_link_npc_think_params_to_speffects(graph):
    goal = Node("lua", "battle", 6520)
    assert {"NpcThinkParam:6520", "NpcThinkParam:6521"} <= {str(e.src) for e in graph.users_of(goal)}
    assert {str(e.dst) for e in graph.refs_of(goal)} == {"SpEffectParam:1500", "SpEffectParam:5444"}


def test_ai_event_script_awards_item_lots(graph):
    assert users(graph, Node.param("ItemLotParam", 5000)) == {
        ("lua/script/global_event:0", "GetRateItem_IgnoreMultiPlay.arg0")
    }


def test_hardcoded_engine_rows(graph):
    assert ("engine/speffect_bonfire_respawn_recovery:0", "hardcoded") in users(graph, Node.param("SpEffectParam", 101))


def test_hardcoded_catalogue_is_valid(baseline):
    import tomllib

    entries = tomllib.loads((CATALOGUE_DIR / "hardcoded.toml").read_text(encoding="utf-8"))["entry"]
    assert len({e["name"] for e in entries}) == len(entries)
    for entry in entries:
        assert entry["param"] in baseline.params and entry["reason"] and entry["source"]


def test_orphan_counts(graph, baseline):
    """Rows nothing references, per param: dead data or engine use not yet catalogued (AUDIT 14). Cataloguing more
    references should lower these deliberately."""
    from ds1rand.graph.build import orphans

    assert {param: len(rows) for param, rows in orphans(graph, baseline).items()} == {
        "SpEffectParam": 334, "Bullet": 76, "AtkParam_Pc": 57, "AtkParam_Npc": 54, "BehaviorParam": 110,
        "BehaviorParam_PC": 18, "Magic": 37, "EquipParamWeapon": 1, "EquipParamProtector": 43,
        "EquipParamAccessory": 0, "EquipParamGoods": 23, "NpcParam": 98, "NpcThinkParam": 91, "ItemLotParam": 105,
        "ObjActParam": 33,
    }
