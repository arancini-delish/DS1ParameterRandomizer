"""TAE (animation event) -> param edges.

Each animation is a node `tae/<model>:<animation ID>`; `model/<model>` links to its animations, so a placed enemy reaches
MSB entry -> model -> animation -> behavior -> attack/bullet -> SpEffect.

Event types and the parameter word holding the reference were determined from vanilla data (see `docs/AUDIT.md` 5):
    1    InvokeAttackBehavior   word 2 = behavior judge ID   (2555/2557 NPC events resolve)
    2    InvokeBulletBehavior   word 2 = behavior judge ID   (1126/1133)
    304  InvokeThrowBehavior    word 1 = behavior judge ID   (164/164; name tentative)
    5    InvokeCommonBehavior   word 1 = BehaviorParam row   (1375/1375; the rows that do not follow the ID formula)
    307  InvokePCBehavior       word 2 = BehaviorParam_PC row (402/420; name tentative)
    66, 67, 302, 401  AddSpEffect variants  word 0 = SpEffectParam row (100%)

Judge IDs are resolved through the model's NPC variations: BehaviorParam rows with `variationId` in the variations of the
NpcParam rows using that model and `behaviorJudgeId` equal to the judge. Which NpcParam rows use a model comes from MSB
placements, else from the ID convention (NpcParam ID < 100000 -> c0000, else c<ID // 100>; edges marked inferred).
The player model c0000 also plays player animations; player judges are resolved by weapon variations in the param graph,
so for c0000 only human NPC variations are linked and unmatched judges are not reported.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

from soulstruct.containers import Binder

from ds1rand.baseline.store import Baseline
from ds1rand.graph.model import Edge, Node, RefGraph, Unresolved
from ds1rand.graph.params import add_reference
from ds1rand.io.tae import TAE

PLAYER_MODEL = "c0000"

JUDGE_EVENTS = {1: ("InvokeAttackBehavior", 2), 2: ("InvokeBulletBehavior", 2), 304: ("InvokeThrowBehavior", 1)}
# event type -> (name, word, params for NPC models, params for the player model)
ROW_EVENTS = {
    5: ("InvokeCommonBehavior", 1, ("BehaviorParam",), ("BehaviorParam_PC", "BehaviorParam")),
    307: ("InvokePCBehavior", 2, ("BehaviorParam_PC",), ("BehaviorParam_PC",)),
    66: ("AddSpEffect66", 0, ("SpEffectParam",), ("SpEffectParam",)),
    67: ("AddSpEffect67", 0, ("SpEffectParam",), ("SpEffectParam",)),
    302: ("AddSpEffect302", 0, ("SpEffectParam",), ("SpEffectParam",)),
    401: ("AddSpEffect401", 0, ("SpEffectParam",), ("SpEffectParam",)),
}


def anibnd_files(chr_dir: Path) -> list[Path]:
    return sorted(chr_dir.glob("c*.anibnd.dcx"))


def model_of(stem: str) -> str:
    """Model name of an anibnd stem, e.g. "c0000_a00_hi" -> "c0000"."""
    return stem.split("_")[0]


def npc_model_by_convention(npc_id: int) -> str:
    return PLAYER_MODEL if npc_id < 100000 else f"c{npc_id // 100:04d}"


def model_variations(baseline: Baseline, prior: RefGraph) -> dict[str, dict[int, str]]:
    """Model -> {NPC behavior variation: confidence}, from MSB placements in `prior`, else the ID convention."""
    npc = baseline.params["NpcParam"]
    variation_index = npc.fields.index("behaviorVariationId")
    placed: dict[int, set[str]] = defaultdict(set)
    entries: dict[Node, list[Edge]] = defaultdict(list)
    for edge in prior.edges:
        if edge.source == "msb":
            entries[edge.src].append(edge)
    for edges in entries.values():
        models = [e.dst.name for e in edges if e.dst.kind == "model"]
        for e in edges:
            if e.dst.name == "NpcParam":
                placed[e.dst.id].update(models)

    variations: dict[str, dict[int, str]] = defaultdict(dict)
    for npc_id, values in npc.rows.items():
        variation = values[variation_index]
        if npc_id == 0 or variation <= 0:
            continue
        if placed.get(npc_id):
            for model in placed[npc_id]:
                variations[model][variation] = "certain"
        else:
            variations[npc_model_by_convention(npc_id)].setdefault(variation, "inferred")
    return variations


def extract_tae_edges(
    files: dict[str, Path], baseline: Baseline, prior: RefGraph, graph: RefGraph | None = None
) -> RefGraph:
    """`files` maps anibnd stems (e.g. "c2230", "c0000_a00_hi") to the file to read."""
    graph = graph if graph is not None else RefGraph()
    logging.getLogger("soulstruct").setLevel(logging.ERROR)
    row_ids = {name: set(pb.rows) for name, pb in baseline.params.items()}
    behaviors = baseline.params["BehaviorParam"]
    by_judge: dict[tuple[int, int], list[int]] = defaultdict(list)
    for row_id in behaviors.rows:
        if row_id:
            values = behaviors.row_values(row_id)
            by_judge[(values["variationId"], values["behaviorJudgeId"])].append(row_id)
    variations = model_variations(baseline, prior)

    seen: set[tuple[Node, str, int]] = set()
    for stem, path in files.items():
        model = model_of(stem)
        is_player = model == PLAYER_MODEL
        for entry in Binder.from_bytes(path.read_bytes()).entries:
            if not entry.name.lower().endswith(".tae"):
                continue
            for animation in TAE.from_bytes(bytes(entry)).animations:
                src = Node("tae", model, animation.id)
                for event in animation.events:
                    if event.type in JUDGE_EVENTS:
                        name, word = JUDGE_EVENTS[event.type]
                        kind = "judge"
                    elif event.type in ROW_EVENTS:
                        name, word, npc_targets, player_targets = ROW_EVENTS[event.type]
                        kind = "row"
                    else:
                        continue
                    if word >= len(event.params):
                        continue
                    value = event.params[word]
                    field = f"{name}.{kind}"
                    if (src, field, value) in seen:
                        continue
                    seen.add((src, field, value))
                    if kind == "row":
                        targets = player_targets if is_player else npc_targets
                        add_reference(graph, row_ids, src, field, value, list(targets), "tae")
                    else:
                        _add_judge(graph, src, field, value, variations.get(model, {}), by_judge, is_player)
                model_node = Node("model", model, 0)
                if (model_node, "animation", animation.id) not in seen:
                    seen.add((model_node, "animation", animation.id))
                    graph.add(Edge(model_node, src, "animation", "tae"))
    return graph


def _add_judge(
    graph: RefGraph,
    src: Node,
    field: str,
    judge: int,
    variations: dict[int, str],
    by_judge: dict[tuple[int, int], list[int]],
    is_player: bool,
) -> None:
    if judge < 0:
        return
    found = False
    for variation, confidence in sorted(variations.items()):
        for row_id in by_judge.get((variation, judge), []):
            graph.add(Edge(src, Node.param("BehaviorParam", row_id), field, "tae", confidence))
            found = True
    if not found and not is_player:
        graph.unresolved.append(Unresolved(src, field, judge, ("BehaviorParam",), "no behavior for judge in model's variations"))
