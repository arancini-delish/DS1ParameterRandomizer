"""EMEVD (event script) -> param edges.

Event scripts are templated: an instruction argument can be replaced by bytes from the arguments a `RunEvent` call
passes to the event. Each event is therefore expanded once per distinct argument block it is run with, starting from
the events no other event runs (the constructors), with replacements applied byte-wise (`read_offset` counts from the
first argument after `RunEvent`'s slot and event ID). Events nobody runs with arguments keep their literal values.

Edges come from `emevd/<file stem>:<event ID>` nodes; the field is `<instruction alias>.<argument name>`.
"""
from __future__ import annotations

import logging
import struct
from collections import defaultdict
from pathlib import Path

from soulstruct.darksouls1ptde.events.emevd.emedf import EMEDF
from soulstruct.darksouls1r.events.emevd.core import EMEVD

from ds1rand.graph.model import Node, RefGraph
from ds1rand.graph.params import add_reference

RUN_EVENT = (2000, 0)
ITEM_PARAMS = {0: "EquipParamWeapon", 1: "EquipParamProtector", 2: "EquipParamAccessory", 3: "EquipParamGoods"}

# (category, index) -> argument name -> params the value can be a row of.
# Not included: obj_act_id arguments (MSB ObjAct entity IDs, not ObjActParam rows; MSB links those to params).
INSTRUCTION_REFS: dict[tuple[int, int], dict[str, tuple[str, ...]]] = {
    (4, 5): {"special_effect": ("SpEffectParam",)},  # IfCharacterSpecialEffectState
    (2004, 8): {"special_effect": ("SpEffectParam",)},  # AddSpecialEffect
    (2004, 21): {"special_effect": ("SpEffectParam",)},  # RemoveSpecialEffect
    (2003, 4): {"item_lot": ("ItemLotParam",)},  # AwardItemLotToAllPlayers
    (2003, 34): {"item_lot": ("ItemLotParam",)},  # SnugglyItemDrop
    (2003, 36): {"item_lot": ("ItemLotParam",)},  # AwardItemLotToHostOnly
    (2003, 5): {"behavior_id": ("BehaviorParam", "BehaviorParam_PC")},  # ShootProjectile; table depends on owner
    (2005, 9): {"behavior_param_id": ("BehaviorParam",)},  # CreateHazard
    (2004, 19): {"ai_param_id": ("NpcThinkParam",)},  # SetAIParamID
    (2003, 12): {"game_area_param_id": ("GameAreaParam",)},  # KillBoss
}
# Instructions with an `item_type` argument selecting which param `item` refers to.
ITEM_INSTRUCTIONS = {(3, 4), (3, 15), (3, 16), (2003, 24)}


def event_files(event_dir: Path) -> list[Path]:
    """`common.emevd.dcx` and the per-map files of the real maps (m10 to m18). The area-level files (e.g.
    `m10.emevd.dcx`) are empty and m99 maps are test maps."""
    maps = sorted(p for p in event_dir.glob("m1*.emevd.dcx") if p.name.count("_") >= 3)
    common = event_dir / "common.emevd.dcx"
    return ([common] if common.is_file() else []) + maps


def extract_emevd_edges(files: dict[str, Path], row_ids: dict[str, set[int]], graph: RefGraph | None = None) -> RefGraph:
    """`files` maps file stems (e.g. "m10_00_00_00") to the file to read, which may be a vanilla backup copy."""
    graph = graph if graph is not None else RefGraph()
    logging.getLogger("soulstruct").setLevel(logging.ERROR)
    for stem, path in files.items():
        _extract_file(EMEVD.from_bytes(path.read_bytes()), stem, row_ids, graph)
    return graph


def _packed_args(instruction) -> bytearray:
    return bytearray(struct.pack("@" + instruction.struct_args_fmt + "0i", *instruction.args_list))


def _extract_file(emevd: EMEVD, stem: str, row_ids: dict[str, set[int]], graph: RefGraph) -> None:
    called = {
        ins.args_list[1]
        for event in emevd.events.values()
        for ins in event.instructions
        if (ins.category, ins.index) == RUN_EVENT
    }
    queue = [(event_id, b"") for event_id in emevd.events if event_id not in called]
    expanded: set[tuple[int, bytes]] = set()
    seen_refs: set[tuple] = set()
    while queue:
        event_id, event_args = queue.pop()
        if (event_id, event_args) in expanded or event_id not in emevd.events:
            continue
        expanded.add((event_id, event_args))
        src = Node("emevd", stem, event_id)
        for ins in emevd.events[event_id].instructions:
            data = _packed_args(ins)
            for repl in ins.event_arg_replacements:
                value = event_args[repl.read_offset:repl.read_offset + repl.size]
                if len(value) == repl.size:
                    data[repl.write_offset:repl.write_offset + repl.size] = value
            key = (ins.category, ins.index)
            if key == RUN_EVENT:
                _slot, target = struct.unpack_from("@iI", data, 0)
                queue.append((target, bytes(data[8:])))
                continue
            if key not in INSTRUCTION_REFS and key not in ITEM_INSTRUCTIONS:
                continue
            spec = EMEDF[key]
            values = dict(zip(spec["args"], struct.unpack("@" + ins.struct_args_fmt + "0i", bytes(data))))
            refs = dict(INSTRUCTION_REFS.get(key, {}))
            if key in ITEM_INSTRUCTIONS and values["item_type"] in ITEM_PARAMS:
                refs["item"] = (ITEM_PARAMS[values["item_type"]],)
            for arg, targets in refs.items():
                field = f"{spec['alias']}.{arg}"
                if (src, field, values[arg]) in seen_refs:
                    continue
                seen_refs.add((src, field, values[arg]))
                add_reference(graph, row_ids, src, field, values[arg], list(targets), "emevd")
