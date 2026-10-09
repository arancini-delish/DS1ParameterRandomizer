"""AI Lua -> param edges, and NpcThinkParam -> AI goal edges.

Each AI goal script is a node `lua/<battle|logic>:<goal ID>` (one node per goal ID even when several maps' luabnds carry
their own copy; edges are the union). Scripts that are not goals (common functions, event scripts) are
`lua/script/<name>:0`. Literal arguments of these calls are param references (found by `ds1rand.io.lua.method_calls`):
    HasSpecialEffectId, IsSleepSpecialEffectId, SetEventSpecialEffect, EraseEventSpecialEffect  arg 1 -> SpEffectParam
    GetRateItem, GetRateItem_IgnoreMultiPlay                                                     arg 0 -> ItemLotParam
NpcThinkParam `logicId` links to the logic goal, `battleGoalID` to the battle goal. (`goalID_ToCaution` / `goalID_ToFind`
are 0 in vanilla except a handful of common goals and are not linked.)
"""
from __future__ import annotations

import logging
from pathlib import Path

from soulstruct.base.ai.luabnd import LuaBND

from ds1rand.baseline.store import Baseline
from ds1rand.graph.model import Edge, Node, RefGraph, Unresolved
from ds1rand.graph.params import NULL_VALUES, add_reference
from ds1rand.io.lua import load_chunk, method_calls

CALL_REFS = {
    "HasSpecialEffectId": (1, "SpEffectParam"),
    "IsSleepSpecialEffectId": (1, "SpEffectParam"),
    "SetEventSpecialEffect": (1, "SpEffectParam"),
    "EraseEventSpecialEffect": (1, "SpEffectParam"),
    "GetRateItem": (0, "ItemLotParam"),
    "GetRateItem_IgnoreMultiPlay": (0, "ItemLotParam"),
}
THINK_GOAL_FIELDS = {"logicId": "logic", "battleGoalID": "battle"}


def luabnd_files(script_dir: Path) -> list[Path]:
    return sorted(script_dir.glob("*.luabnd.dcx"))


def goal_node(goal_type: str, goal_id: int) -> Node:
    return Node("lua", goal_type, goal_id)


def extract_lua_edges(
    files: dict[str, Path], baseline: Baseline, prior: RefGraph, graph: RefGraph | None = None
) -> RefGraph:
    """`files` maps luabnd stems (e.g. "aiCommon", "m10_00_00_00") to the file to read."""
    graph = graph if graph is not None else RefGraph()
    logging.getLogger("soulstruct").setLevel(logging.ERROR)
    row_ids = {name: set(pb.rows) for name, pb in baseline.params.items()}
    goals: set[tuple[str, int]] = set()
    seen: set[tuple[Node, str, object]] = set()

    for path in files.values():
        luabnd = LuaBND.from_bytes(path.read_bytes())
        scripts = [(goal_node(g.goal_type.value, g.goal_id), g.bytecode) for g in luabnd.goals]
        goals.update((g.goal_type.value, g.goal_id) for g in luabnd.goals)
        scripts += [(Node("lua", f"script/{s.name}", 0), s.bytecode) for s in luabnd.unknown_scripts]
        for src, bytecode in scripts:
            if not bytecode.startswith(b"\x1bLua"):
                continue
            for call in method_calls(load_chunk(bytecode)):
                if call.name not in CALL_REFS:
                    continue
                index, param = CALL_REFS[call.name]
                value = call.args[index] if index < len(call.args) else None
                field = f"{call.name}.arg{index}"
                if not isinstance(value, int) or (src, field, value) in seen:
                    continue
                seen.add((src, field, value))
                add_reference(graph, row_ids, src, field, value, [param], "lua")

    think = baseline.params["NpcThinkParam"]
    for row_id in think.rows:
        values = think.row_values(row_id)
        for field, goal_type in THINK_GOAL_FIELDS.items():
            goal_id = values[field]
            if goal_id in NULL_VALUES:
                continue
            src = Node.param("NpcThinkParam", row_id)
            if (goal_type, goal_id) in goals:
                graph.add(Edge(src, goal_node(goal_type, goal_id), field, "lua"))
            else:
                graph.unresolved.append(Unresolved(src, field, goal_id, (f"lua {goal_type} goal",), "no such goal"))
    return graph
