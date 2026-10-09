"""Row budgets: what decoupling features costs, what cannot be decoupled, and where new rows go (Phase 4c).

Decoupling. A row shared by several features can be copied so each feature edits its own row, but only references
that are param fields holding a single possible row ID (`is_repointable`) can be pointed at a copy. References from game files
(EMEVD, MSB, TAE, AI Lua), engine-hardcoded IDs and computed IDs (behavior rows found by variation + judge ID) are
fixed: the features reaching a row that way must keep the original. A feature also shares a row with every feature
that shares the referencing row's copy. `decoupling` computes, per row, the partition of its features into groups that
must share one row (union-find, iterated to a fixpoint); the group holding fixed references keeps the original ID.
    copies needed = groups - 1      coupled = groups with more than one feature (cannot be separated)
Behavior rows reached through a shared variation stay coupled; separating them would need a whole-variation copy
(new variationId with copies of all its behaviors), which is a possible later extension.

New rows. Copies and extra rows for compounding chains are appended under new IDs, from `NEW_ID_BLOCKS`, which are
empty in vanilla and away from documented ID ranges. A new row must fit the narrowest field that will reference it:
`Magic.refId` and `Magic.replaceMagicId` are s16 (spell root Bullet / SpEffect / AtkParam_Pc / Magic rows must be
<= 32767), upgrade-level SpEffect fields are u8 and ObjAct SpEffect fields u16. `RowBudget` caps new rows per param
(None = unbounded); a cap of 0 means reuse only, and decoupling then stops where the cap runs out.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from ds1rand.baseline.store import Baseline
from ds1rand.catalogue.usage import compute_usage, is_usage_edge
from ds1rand.defs.paramdef import load_paramdefs
from ds1rand.graph.model import Node, RefGraph
from ds1rand.graph.params import field_refs

REPOINTABLE_SOURCES = {"meta", "soulstruct"}


def is_repointable(edge) -> bool:
    """A param field holding exactly one possible target row ID. Ambiguous fields (e.g. a Bullet attack ID that exists
    as both an AtkParam_Pc and an AtkParam_Npc row) cannot change value for one target without breaking the other."""
    return edge.source in REPOINTABLE_SOURCES and edge.confidence == "certain"
BUDGET_PARAMS = ("Magic", "Bullet", "AtkParam_Pc", "AtkParam_Npc", "SpEffectParam", "BehaviorParam",
                 "BehaviorParam_PC", "EquipParamWeapon", "EquipParamGoods", "EquipParamAccessory", "NpcThinkParam")

TYPE_MAX = {"s8": 127, "u8": 255, "s16": 32767, "u16": 65535, "s32": 2**31 - 1, "u32": 2**31 - 1}
# (first, last) blocks of new row IDs, narrow block first. Both are empty in vanilla for every param.
NEW_ID_BLOCKS = ((30000, 32767), (9_000_000, 9_999_999))


@dataclass
class RowGroups:
    """Partition of one row's features into groups that must share a row."""
    groups: list[frozenset[str]]
    original: frozenset[str] | None  # group that must keep the original ID (fixed references), if any

    @property
    def copies_needed(self) -> int:
        return len(self.groups) - 1

    @property
    def coupled(self) -> list[frozenset[str]]:
        return [g for g in self.groups if len(g) > 1]


class _UnionFind:
    def __init__(self, items):
        self.parent = {i: i for i in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, items) -> bool:
        roots = {self.find(i) for i in items}
        if len(roots) < 2:
            return False
        first, *rest = roots
        for r in rest:
            self.parent[r] = first
        return True

    def groups(self) -> list[frozenset]:
        by_root = defaultdict(set)
        for item in self.parent:
            by_root[self.find(item)].add(item)
        return sorted((frozenset(g) for g in by_root.values()), key=sorted)


def decoupling(
    graph: RefGraph,
    baseline: Baseline,
    extra_merges: dict[Node, list[set[str]]] | None = None,
    usage: dict[Node, set[str]] | None = None,
    anchors: dict[Node, set[str]] | None = None,
) -> dict[Node, RowGroups]:
    """Feature groups per used param row (rows used by a single feature have one group). `extra_merges` forces
    further features to share a row (e.g. features that are not being randomized, or copies a cap cannot afford);
    `anchors` names features that must keep a row's original ID (e.g. items the player owns by ID)."""
    usage = usage if usage is not None else compute_usage(graph, baseline, all_nodes=True)
    sets = {node: _UnionFind(features) for node, features in usage.items()}
    for node, merges in (extra_merges or {}).items():
        for merge in merges:
            sets[node].union(merge & usage.get(node, set()))
    fixed: dict[Node, set[str]] = defaultdict(set)
    for node, features in usage.items():
        if node.kind != "param":
            continue
        for edge in graph.users_of(node):
            if is_usage_edge(edge) and not is_repointable(edge):
                fixed[node] |= usage.get(edge.src, set()) & features
    for node, features in (anchors or {}).items():
        fixed[node] |= features & usage.get(node, set())
    for node, features in fixed.items():
        sets[node].union(features)

    changed = True
    while changed:
        changed = False
        for node, features in usage.items():
            if node.kind != "param":
                continue
            for edge in graph.users_of(node):
                if not is_usage_edge(edge) or edge.src not in sets:
                    continue
                for group in sets[edge.src].groups():
                    if sets[node].union(group & features):
                        changed = True

    result = {}
    for node, features in usage.items():
        if node.kind != "param":
            continue
        groups = sets[node].groups()
        original = next((g for g in groups if g & fixed.get(node, set())), None)
        result[node] = RowGroups(groups, original)
    return result


@dataclass
class ParamBudget:
    param: str
    used: int = 0
    footprint: Counter = field(default_factory=Counter)  # feature -> rows it uses
    copies_needed: int = 0
    coupled_rows: int = 0
    coupled_groups: Counter = field(default_factory=Counter)  # frozenset of features -> rows


def param_budgets(graph: RefGraph, baseline: Baseline, params=BUDGET_PARAMS) -> dict[str, ParamBudget]:
    budgets = {p: ParamBudget(p) for p in params}
    for node, rows in decoupling(graph, baseline).items():
        if node.name not in budgets:
            continue
        budget = budgets[node.name]
        budget.used += 1
        for group in rows.groups:
            for feature in group:
                budget.footprint[feature] += 1
        budget.copies_needed += rows.copies_needed
        if rows.coupled:
            budget.coupled_rows += 1
            for group in rows.coupled:
                budget.coupled_groups[group] += 1
    return budgets


def unit_footprint(graph: RefGraph, root: Node, params=BUDGET_PARAMS) -> Counter:
    """Rows per param that one root (e.g. a spell's Magic row) reaches through usage edges, including itself."""
    seen = {root}
    stack = [root]
    while stack:
        for edge in graph.refs_of(stack.pop()):
            if edge.dst not in seen and is_usage_edge(edge):
                seen.add(edge.dst)
                stack.append(edge.dst)
    return Counter(n.name for n in seen if n.kind == "param" and n.name in params)


def reference_limits(baseline: Baseline) -> dict[str, dict[tuple[str, str], int]]:
    """Target param -> {(referencing param, field): largest row ID the field can hold}."""
    defs = load_paramdefs()
    limits: dict[str, dict[tuple[str, str], int]] = defaultdict(dict)
    for src, fields in field_refs(baseline).items():
        types = {f.name: f.type for f in defs[baseline.manifest["params"][src]["param_type"]].fields}
        for field_name, targets in fields.items():
            for target in targets:
                limits[target.param][(src, field_name)] = TYPE_MAX.get(types[field_name], 2**31 - 1)
    return limits


class IdAllocator:
    """Hands out unused row IDs from `NEW_ID_BLOCKS`, never reusing vanilla IDs or IDs already handed out. The widest
    block that fits `max_id` is used first, keeping the small narrow block for rows that must fit 16-bit fields."""

    def __init__(self, baseline: Baseline):
        self.taken = {name: set(pb.rows) for name, pb in baseline.params.items()}

    def allocate(self, param: str, max_id: int = 2**31 - 1, step: int = 1) -> int:
        """Lowest free ID; `step` > 1 returns a multiple of `step` (weapon/armor IDs are multiples of 100)."""
        for first, last in reversed(NEW_ID_BLOCKS):
            if first > max_id:
                continue
            for row_id in range(-(-first // step) * step, min(last, max_id) + 1, step):
                if row_id not in self.taken[param]:
                    self.taken[param].add(row_id)
                    return row_id
        raise ValueError(f"No free {param} row ID <= {max_id}")

    def capacity(self, param: str, max_id: int = 2**31 - 1) -> int:
        return sum(
            max(0, min(last, max_id) - first + 1) - sum(1 for r in self.taken[param] if first <= r <= min(last, max_id))
            for first, last in NEW_ID_BLOCKS if first <= max_id
        )


@dataclass
class RowBudget:
    """New-row caps per param (None = unbounded; 0 = reuse only). `default` applies to params not listed."""
    caps: dict[str, int | None] = field(default_factory=dict)
    default: int | None = None

    def cap(self, param: str) -> int | None:
        return self.caps.get(param, self.default)

    def plan(self, budgets: dict[str, ParamBudget]) -> dict[str, dict[str, int | None]]:
        """Per param: new rows needed for full decoupling, the cap, rows the cap leaves for compounding chains
        (None if unbounded), and the decoupling shortfall if the cap is too small."""
        plan = {}
        for param, budget in budgets.items():
            cap = self.cap(param)
            needed = budget.copies_needed
            plan[param] = {
                "decoupling": needed,
                "cap": cap,
                "surplus": None if cap is None else max(0, cap - needed),
                "shortfall": 0 if cap is None else max(0, needed - cap),
            }
        return plan
