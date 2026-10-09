"""Param -> param edges, extracted from the vanilla baseline.

Sources:
    meta                `Refs` in `ds1paramdefs/Meta`, including conditional refs (`Bullet(refCategory=1)`)
    soulstruct          references soulstruct's paramdefs annotate that Meta lacks (`EXTRA_REFS`)
    behavior_variation  EquipParamWeapon/NpcParam `behaviorVariationId` -> every BehaviorParam(_PC) row with that
                        `variationId`. Behavior row IDs are 100000000 (player) / 200000000 (NPC) + variation * 1000 +
                        judge ID, but some vanilla behavior rows do not follow that formula, so the field is matched.

A reference value of -1 or 0 means "none": row 0 of every param is a dummy/test row.

Weapon and armor IDs encode the upgrade level in the last two digits: only the base row of each upgrade path exists
(e.g. 100000, or 100100 for an infusion path), and 100005 means that path at +5. References to those params resolve to
`value - value % 100` when the exact row does not exist.
"""
from __future__ import annotations

from collections import defaultdict

from ds1rand.baseline.store import Baseline
from ds1rand.defs.meta import RefTarget, load_meta
from ds1rand.defs.paramdef import load_paramdefs
from ds1rand.graph.model import Edge, Node, RefGraph, Unresolved

# Meta `Refs` names that are not the real param names.
PARAM_ALIASES = {"BehaviorParam_Pc": "BehaviorParam_PC", "QwcChangeParam": "QwcChange"}

# Fields soulstruct annotates as references but Meta does not. Magic/Goods/Accessory `behaviorId` are also annotated
# by soulstruct but are 0 in every vanilla row, so they are left out.
EXTRA_REFS: dict[str, dict[str, tuple[RefTarget, ...]]] = {
    "ReinforceParamWeapon": {
        f: (RefTarget("SpEffectParam"),)
        for f in ("spEffectId1", "spEffectId2", "spEffectId3",
                  "residentSpEffectId1", "residentSpEffectId2", "residentSpEffectId3")
    },
    "ReinforceParamProtector": {
        **{f: (RefTarget("SpEffectParam"),) for f in ("residentSpEffectId1", "residentSpEffectId2", "residentSpEffectId3")},
        "materialSetId": (RefTarget("EquipMtrlSetParam"),),
    },
    "Magic": {"replaceMagicId": (RefTarget("Magic"),)},
    "SpEffectVfxParam": {
        "transformProtectorId": (RefTarget("EquipParamProtector"),),
        "isFullBodyTransformProtectorId": (RefTarget("EquipParamProtector"),),
    },
}

# When a field may reference either the player or NPC version of a param, the referencing param decides which.
PLAYER_SIDE = {"BehaviorParam_PC", "AtkParam_Pc", "EquipParamWeapon", "EquipParamGoods", "EquipParamAccessory",
               "EquipParamProtector", "Magic", "CharaInitParam"}
NPC_SIDE = {"BehaviorParam", "AtkParam_Npc", "NpcParam"}
_SIDED = {"AtkParam_Pc": "AtkParam_Npc", "BehaviorParam_PC": "BehaviorParam"}

NULL_VALUES = (-1, 0)
UPGRADEABLE = {"EquipParamWeapon", "EquipParamProtector"}


def _find_row(param: str, value: int, row_ids: set[int]) -> int | None:
    """Row ID that `value` refers to in `param`, accounting for upgrade levels; None if absent."""
    if value in row_ids:
        return value
    if param in UPGRADEABLE and (base := value - value % 100) in row_ids:
        return base
    return None


def _resolve_side(source_param: str, targets: list[str]) -> list[str]:
    for player, npc in _SIDED.items():
        if player in targets and npc in targets:
            if source_param in PLAYER_SIDE:
                targets = [t for t in targets if t != npc]
            elif source_param in NPC_SIDE:
                targets = [t for t in targets if t != player]
    return targets


def field_refs(baseline: Baseline) -> dict[str, dict[str, tuple[RefTarget, ...]]]:
    """Param name -> field name -> reference targets (Meta plus `EXTRA_REFS`), with param names normalised."""
    defs = load_paramdefs()
    meta = load_meta()
    refs: dict[str, dict[str, tuple[RefTarget, ...]]] = {}
    for name, info in baseline.manifest["params"].items():
        param_meta = meta.get(defs[info["param_type"]].stem)
        fields = {f: m.refs for f, m in param_meta.fields.items() if m.refs} if param_meta else {}
        fields.update(EXTRA_REFS.get(name, {}))
        refs[name] = {
            f: tuple(RefTarget(PARAM_ALIASES.get(t.param, t.param), t.condition_field, t.condition_value) for t in ts)
            for f, ts in fields.items()
        }
    return refs


def extract_param_edges(baseline: Baseline, graph: RefGraph | None = None) -> RefGraph:
    graph = graph if graph is not None else RefGraph()
    row_ids = {name: set(pb.rows) for name, pb in baseline.params.items()}

    for name, fields in field_refs(baseline).items():
        pb = baseline.params[name]
        for row_id in pb.rows:
            row = pb.row_values(row_id)
            src = Node.param(name, row_id)
            for field, targets in fields.items():
                value = row[field]
                if value in NULL_VALUES:
                    continue
                candidates = _resolve_side(name, [t.param for t in targets if t.applies(row)])
                if not candidates:
                    continue  # condition selects no target (e.g. a category this field does not reference)
                source = "soulstruct" if field in EXTRA_REFS.get(name, {}) else "meta"
                add_reference(graph, row_ids, src, field, value, candidates, source)

    _behavior_variation_edges(baseline, graph)
    return graph


def add_reference(
    graph: RefGraph,
    row_ids: dict[str, set[int]],
    src: Node,
    field: str,
    value: int,
    candidates: list[str],
    source: str,
    optional: bool = False,
) -> None:
    """Add edges from `src` to the row `value` in each candidate param that has it (ambiguous if several), or record
    it as unresolved unless `optional` (a missing row is normal, e.g. objects without ObjectParam rows). Null values
    are ignored."""
    if value in NULL_VALUES:
        return
    found = [(t, r) for t in candidates if (r := _find_row(t, value, row_ids[t])) is not None]
    if not found:
        if not optional:
            graph.unresolved.append(Unresolved(src, field, value, tuple(candidates), "missing row"))
        return
    confidence = "certain" if len(found) == 1 else "ambiguous"
    for target, target_id in found:
        graph.add(Edge(src, Node.param(target, target_id), field, source, confidence))


def _behavior_variation_edges(baseline: Baseline, graph: RefGraph) -> None:
    for owner, behavior in (("EquipParamWeapon", "BehaviorParam_PC"), ("NpcParam", "BehaviorParam")):
        by_variation: dict[int, list[int]] = defaultdict(list)
        bp = baseline.params[behavior]
        index = bp.fields.index("variationId")
        for row_id, values in bp.rows.items():
            if row_id != 0:
                by_variation[values[index]].append(row_id)

        owner_param = baseline.params[owner]
        index = owner_param.fields.index("behaviorVariationId")
        for row_id, values in owner_param.rows.items():
            variation = values[index]
            if variation in NULL_VALUES:
                continue
            src = Node.param(owner, row_id)
            behaviors = by_variation.get(variation)
            if not behaviors:
                # Vanilla: test/passive NPCs and severed parts (tails, heads). TAE confirms severed-part models invoke no
                # behaviors; their body's model and variation do the attacking.
                graph.unresolved.append(
                    Unresolved(src, "behaviorVariationId", variation, (behavior,), "no behaviors with this variation")
                )
                continue
            for behavior_id in behaviors:
                graph.add(Edge(src, Node.param(behavior, behavior_id), "behaviorVariationId", "behavior_variation"))
