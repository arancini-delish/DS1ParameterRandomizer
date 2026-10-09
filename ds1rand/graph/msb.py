"""MSB (map layout) -> param edges.

Sources are `msb/<map>/<entry name>:<entity ID>` nodes (entity ID -1 when the entry has none; entry names repeated in a
map get a `#2`, `#3`... suffix):
    characters (incl. dummy characters)  character_id -> NpcParam, ai_id -> NpcThinkParam, player_id -> CharaInitParam,
                                         and model -> `model/cXXXX:0` (links NPCs to animation data in 3c)
    objects (incl. dummy objects)        model oXXXX -> ObjectParam row XXXX (many objects have none; not reported)
    treasure events                      item_lot_1..5 -> ItemLotParam
    ObjAct events                        obj_act_param_id -> ObjActParam
Only the real maps (m10 to m18) are read; m99 maps are test maps.
"""
from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

from soulstruct.darksouls1r.maps import MSB

from ds1rand.graph.model import Edge, Node, RefGraph
from ds1rand.graph.params import add_reference

CHARACTER_REFS = {"character_id": "NpcParam", "ai_id": "NpcThinkParam", "player_id": "CharaInitParam"}


def map_files(map_dir: Path) -> list[Path]:
    return sorted(p for p in map_dir.glob("m1*.msb"))


def extract_msb_edges(files: dict[str, Path], row_ids: dict[str, set[int]], graph: RefGraph | None = None) -> RefGraph:
    """`files` maps map stems (e.g. "m10_00_00_00") to the file to read, which may be a vanilla backup copy."""
    graph = graph if graph is not None else RefGraph()
    logging.getLogger("soulstruct").setLevel(logging.ERROR)
    for stem, path in files.items():
        _extract_map(MSB.from_bytes(path.read_bytes()), stem, row_ids, graph)
    return graph


def _extract_map(msb: MSB, map_stem: str, row_ids: dict[str, set[int]], graph: RefGraph) -> None:
    name_counts: Counter[str] = Counter()

    def _node(entry) -> Node:
        name_counts[entry.name] += 1
        suffix = f"#{name_counts[entry.name]}" if name_counts[entry.name] > 1 else ""
        entity_id = entry.entity_id if entry.entity_id is not None else -1
        return Node("msb", f"{map_stem}/{entry.name}{suffix}", entity_id)

    for character in list(msb.characters) + list(msb.dummy_characters):
        src = _node(character)
        for attr, param in CHARACTER_REFS.items():
            if hasattr(character, attr):
                add_reference(graph, row_ids, src, attr, getattr(character, attr), [param], "msb")
        if character.model:
            graph.add(Edge(src, Node("model", character.model.name, 0), "model", "msb"))

    for obj in list(msb.objects) + list(msb.dummy_objects):
        if obj.model:
            model_id = int(obj.model.name[1:])
            add_reference(graph, row_ids, _node(obj), "model", model_id, ["ObjectParam"], "msb", optional=True)

    for treasure in msb.treasures:
        src = _node(treasure)
        for i in range(1, 6):
            lot = getattr(treasure, f"item_lot_{i}")
            add_reference(graph, row_ids, src, f"item_lot_{i}", lot, ["ItemLotParam"], "msb")

    for obj_act in msb.obj_acts:
        add_reference(graph, row_ids, _node(obj_act), "obj_act_param_id", obj_act.obj_act_param_id, ["ObjActParam"],
                      "msb")
