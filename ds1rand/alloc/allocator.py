"""Decoupling shared rows: copy them for the features being randomized and repoint those features' references.

`allocate(enabled features, budget)`:
1. Partition each used row's features into groups that must share a row (`catalogue.budget.decoupling`), with every
   feature that is not enabled merged into one group: features that are not randomized keep using the original rows
   and cost no copies.
2. Per row, the group with fixed references keeps the original ID: references from game files, the engine and
   computed IDs, and a feature's own root rows (items the player owns, finds and equips by ID: weapons, armor, rings,
   goods, spells; saves, item lots and shops refer to those IDs). Failing that
   the group of non-enabled features; failing that the group whose best feature has the lowest priority. Every other
   group gets a copy.
3. If a param's copies exceed its `RowBudget` cap, the lowest-priority copy groups are merged into the row's keeper
   group and the partition is recomputed, until every param fits. Features merged this way stay coupled: the cost of
   a small cap.
4. Copies get new IDs from `IdAllocator`, small enough for every field that will reference them (Magic.refId is s16)
   and multiples of 100 for weapon/armor rows (upgrade levels are encoded in the last two digits). Rows referenced by
   a field too narrow for any new-ID block (e.g. u8) cannot be copied: their features stay coupled.
5. References are repointed group by group: each copy of a referencing row points at the copy of the referenced row
   that its features use, keeping any upgrade-level offset in the value.
Priority is the order of `enabled`: earlier features win copies when a cap runs out. `params` limits copying to the
params the randomizers will edit (default: all); rows of other params stay shared. Rows the store protects (repeated
IDs) are never copied. `rows` further limits copying to those rows (e.g. what one randomizer reaches).

The result tells each feature which rows it may edit alone (`owned`) and which it still shares (`coupled`).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ds1rand.alloc.store import RowStore
from ds1rand.baseline.store import Baseline
from ds1rand.catalogue.budget import (
    NEW_ID_BLOCKS, IdAllocator, RowBudget, RowGroups, decoupling, is_repointable, reference_limits,
)
from ds1rand.catalogue.usage import compute_usage, feature_roots, is_usage_edge
from ds1rand.graph.model import Node, RefGraph
from ds1rand.graph.params import UPGRADEABLE

MAX_ID = 2**31 - 1


@dataclass
class Allocation:
    enabled: tuple[str, ...]
    groups: dict[Node, RowGroups]
    row_ids: dict[tuple[Node, frozenset[str]], int]  # (original row, group) -> row ID that group uses
    copies: dict[str, int] = field(default_factory=dict)  # param -> copies made

    def row_for(self, node: Node, feature: str) -> int:
        """The row ID `feature` uses in place of the original row `node`."""
        for group in self.groups[node].groups:
            if feature in group:
                return self.row_ids[(node, group)]
        raise KeyError(f"{feature} does not use {node}")

    def owned(self, feature: str) -> dict[str, set[int]]:
        """Param -> row IDs only `feature` uses: it may edit these freely."""
        result: dict[str, set[int]] = defaultdict(set)
        for node, row_groups in self.groups.items():
            for group in row_groups.groups:
                if group == {feature}:
                    result[node.name].add(self.row_ids[(node, group)])
        return dict(result)

    def coupled(self, feature: str) -> dict[tuple[str, int], frozenset[str]]:
        """(param, row ID) -> the other features sharing that row with `feature`."""
        result = {}
        for node, row_groups in self.groups.items():
            for group in row_groups.groups:
                if feature in group and len(group) > 1:
                    result[(node.name, self.row_ids[(node, group)])] = group - {feature}
        return result


def _priority(group: frozenset[str], enabled: tuple[str, ...]) -> int:
    """Lower is more important: index of the group's most important enabled feature."""
    return min((enabled.index(f) for f in group if f in enabled), default=len(enabled))


def _keeper(row_groups: RowGroups, enabled: tuple[str, ...]) -> frozenset[str]:
    if row_groups.original is not None:
        return row_groups.original
    disabled = [g for g in row_groups.groups if not g & set(enabled)]
    if disabled:
        return disabled[0]
    return max(row_groups.groups, key=lambda g: (_priority(g, enabled), sorted(g)))


def copy_id_limit(graph: RefGraph, node: Node, limits: dict) -> int:
    """Largest ID a copy of `node` may have: the narrowest repointable field referencing it."""
    return min(
        (limits[node.name].get((e.src.name, e.field), MAX_ID) for e in graph.users_of(node)
         if is_repointable(e) and is_usage_edge(e) and e.src.kind == "param"),
        default=MAX_ID,
    )


def plan_groups(
    graph: RefGraph,
    baseline: Baseline,
    enabled: tuple[str, ...],
    budget: RowBudget,
    params: set[str] | None = None,
    protected: dict[str, set[int]] | None = None,
    rows: set[Node] | None = None,
) -> dict[Node, RowGroups]:
    usage = compute_usage(graph, baseline, all_nodes=True)
    limits = reference_limits(baseline)
    merges: dict[Node, list[set[str]]] = {
        node: [features - set(enabled)] for node, features in usage.items() if node.kind == "param"
    }
    for node, features in usage.items():
        if node.kind != "param":
            continue
        if (params is not None and node.name not in params) or (rows is not None and node not in rows):
            merges[node].append(set(features))  # not edited: no need to copy
        elif node.id in (protected or {}).get(node.name, set()):
            merges[node].append(set(features))  # repeated ID: cannot be copied
        elif copy_id_limit(graph, node, limits) < NEW_ID_BLOCKS[0][0]:
            merges[node].append(set(features))  # no new ID fits: cannot be copied
    anchors: dict[Node, set[str]] = defaultdict(set)
    for feature, roots in feature_roots(graph, baseline).items():
        for node in roots:
            if node.kind == "param":
                anchors[node].add(feature)
    while True:
        groups = decoupling(graph, baseline, merges, usage, anchors)
        changed = False
        # Non-enabled features share the original row.
        for node, row_groups in groups.items():
            disabled = set().union(*row_groups.groups) - set(enabled)
            keeper = _keeper(row_groups, enabled)
            if disabled and not disabled <= keeper:
                merges[node].append(set(disabled | keeper))
                changed = True
        # Caps: merge the lowest-priority copy groups into the keeper.
        if not changed:
            by_param: dict[str, list[tuple[int, Node, frozenset[str]]]] = defaultdict(list)
            for node, row_groups in groups.items():
                keeper = _keeper(row_groups, enabled)
                for group in row_groups.groups:
                    if group != keeper:
                        by_param[node.name].append((_priority(group, enabled), node, group))
            for param, candidates in by_param.items():
                cap = budget.cap(param)
                if cap is None or len(candidates) <= cap:
                    continue
                for _, node, group in sorted(candidates, key=lambda c: (c[0], c[1], sorted(c[2])))[cap:]:
                    merges[node].append(set(group | _keeper(groups[node], enabled)))
                changed = True
        if not changed:
            return groups


def allocate(
    graph: RefGraph,
    baseline: Baseline,
    store: RowStore,
    enabled: list[str] | tuple[str, ...],
    budget: RowBudget | None = None,
    ids: IdAllocator | None = None,
    params: set[str] | None = None,
    rows: set[Node] | None = None,
) -> Allocation:
    enabled = tuple(enabled)
    budget = budget or RowBudget()
    ids = ids or IdAllocator(baseline)
    groups = plan_groups(graph, baseline, enabled, budget, params, store.protected, rows)
    limits = reference_limits(baseline)

    allocation = Allocation(enabled, groups, {})
    for node in sorted(groups):
        row_groups = groups[node]
        keeper = _keeper(row_groups, enabled)
        for group in row_groups.groups:
            if group == keeper:
                allocation.row_ids[(node, group)] = node.id
                continue
            max_id = copy_id_limit(graph, node, limits)
            new_id = ids.allocate(node.name, max_id, step=100 if node.name in UPGRADEABLE else 1)
            store.add(node.name, new_id, copy_from=node.id)
            allocation.row_ids[(node, group)] = new_id
            allocation.copies[node.name] = allocation.copies.get(node.name, 0) + 1

    for node in sorted(groups):
        for edge in graph.users_of(node):
            if not (is_usage_edge(edge) and is_repointable(edge) and edge.src in groups):
                continue
            for src_group in groups[edge.src].groups:
                features = src_group & set().union(*groups[node].groups)
                if not features:
                    continue
                target = allocation.row_for(node, next(iter(sorted(features))))
                if target == node.id:
                    continue
                src_row = allocation.row_ids[(edge.src, src_group)]
                value = store.values(edge.src.name, src_row)[edge.field]
                store.set(edge.src.name, src_row, {edge.field: target + (value - node.id)})
    return allocation
