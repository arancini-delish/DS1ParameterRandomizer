"""Which features use each param row.

A feature is a set of root nodes plus everything reachable from them through "usage" edges. A row reached from several
features is shared: randomizing it for one feature changes the others, so the allocator must decouple it.

Features:
    ring               EquipParamAccessory rows
    player_spell       Magic rows referenced by EquipParamGoods (the 72 player spells; spell items)
    player_weapon      EquipParamWeapon rows (melee, ammo, bows, catalysts, talismans)
    player_goods       EquipParamGoods rows (consumables, throwables); stops at player spells
    player_armor       EquipParamProtector rows
    player_animation   player model (c0000) animation events: rolls, item use, etc.
    enemy              NpcParam rows, placed characters, non-player animations, AI goal scripts
    environment        event scripts, placed objects and ObjActs, event Lua scripts
    engine             curated engine-hardcoded references

Usage does not flow through grants: item lots, shops, upgrade materials, upgrade paths, `originEquip*` /
`wanderingEquip*` fields and EMEVD inventory checks give or inspect an item; they are not that item being used.
Player model (c0000) animations are shared by the player and human NPCs: their links into NPC behavior rows count as
`enemy`. Human NPCs (NpcParam ID < 100000) mostly have behavior variation 0 and attack through their equipped weapons'
player behaviors, so `enemy` -> CharaInitParam -> weapon -> BehaviorParam_PC sharing is real.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable

from ds1rand.baseline.store import Baseline
from ds1rand.graph.model import Edge, Node, RefGraph

FEATURES = (
    "ring", "player_spell", "player_weapon", "player_goods", "player_armor", "player_animation", "enemy",
    "environment", "engine",
)
GRANT_PARAMS = {"ItemLotParam", "ShopLineupParam", "EquipMtrlSetParam"}
GRANT_SOURCES = {"upgrade_path", "item_lot_chain"}
GRANT_FIELD_PREFIXES = (
    "originEquip", "wanderingEquip",
    # EMEVD inventory checks and removal: the event looks at the player's items, it does not use them.
    "IfPlayerItemState", "IfItemDropped", "RemoveItemFromPlayer",
)
PLAYER_MODEL = "c0000"


def is_usage_edge(edge: Edge) -> bool:
    return not (
        (edge.dst.kind == "param" and edge.dst.name in GRANT_PARAMS)
        or edge.source in GRANT_SOURCES
        or edge.field.startswith(GRANT_FIELD_PREFIXES)
    )


def _params(baseline: Baseline, name: str) -> set[Node]:
    return {Node.param(name, r) for r in baseline.params[name].rows if r}


def feature_roots(graph: RefGraph, baseline: Baseline) -> dict[str, set[Node]]:
    nodes = graph.nodes
    spells = {
        e.dst for e in graph.edges if e.src.name == "EquipParamGoods" and e.dst.name == "Magic" and e.dst.kind == "param"
    }
    return {
        "ring": _params(baseline, "EquipParamAccessory"),
        "player_spell": spells,
        "player_weapon": _params(baseline, "EquipParamWeapon"),
        "player_goods": _params(baseline, "EquipParamGoods"),
        "player_armor": _params(baseline, "EquipParamProtector"),
        "player_animation": {n for n in nodes if n.kind == "tae" and n.name == PLAYER_MODEL},
        "enemy": _params(baseline, "NpcParam")
        | {n for n in nodes if n.kind == "tae" and n.name != PLAYER_MODEL}
        | {n for n in nodes if n.kind == "lua" and not n.name.startswith("script/")}
        | {e.src for e in graph.edges if e.src.kind == "msb" and e.field in ("character_id", "ai_id", "player_id")},
        "environment": {n for n in nodes if n.kind == "emevd"}
        | {n for n in nodes if n.kind == "lua" and n.name.startswith("script/")}
        | {e.src for e in graph.edges if e.src.kind == "msb" and e.field in ("model", "obj_act_param_id")
           and e.dst.kind == "param"},
        "engine": {n for n in nodes if n.kind == "engine"},
    }


# Per feature: extra edges not to follow (beyond grants), and nodes to stop at (not entered).
_PLAYER_SIDE_OF_C0000: Callable[[Edge], bool] = lambda e: not (
    e.src.kind == "tae" and e.src.name == PLAYER_MODEL and e.dst.name == "BehaviorParam"
)
_ENEMY_SIDE_OF_C0000: Callable[[Edge], bool] = lambda e: not (
    e.src.kind == "tae" and e.src.name == PLAYER_MODEL and e.dst.name != "BehaviorParam"
)


def compute_usage(graph: RefGraph, baseline: Baseline, all_nodes: bool = False) -> dict[Node, set[str]]:
    """Param row -> features that use it (every reached node, including non-param ones, if `all_nodes`)."""
    roots = feature_roots(graph, baseline)
    edge_filters: dict[str, Callable[[Edge], bool]] = {
        "player_animation": _PLAYER_SIDE_OF_C0000,
        "enemy": _ENEMY_SIDE_OF_C0000,
    }
    stop_at = {"player_goods": roots["player_spell"]}
    enemy_c0000 = {n for n in graph.nodes if n.kind == "tae" and n.name == PLAYER_MODEL}

    usage: dict[Node, set[str]] = defaultdict(set)
    for feature in FEATURES:
        allowed = edge_filters.get(feature, lambda e: True)
        stops = stop_at.get(feature, set())
        start = set(roots[feature]) | (enemy_c0000 if feature == "enemy" else set())
        seen = set(start)
        stack = list(start)
        while stack:
            for edge in graph.refs_of(stack.pop()):
                if edge.dst in seen or edge.dst in stops or not is_usage_edge(edge) or not allowed(edge):
                    continue
                seen.add(edge.dst)
                stack.append(edge.dst)
        for node in seen:
            if all_nodes or node.kind == "param":
                usage[node].add(feature)
    return dict(usage)


def shared_rows(usage: dict[Node, set[str]]) -> dict[Node, set[str]]:
    return {node: features for node, features in usage.items() if len(features) > 1}
