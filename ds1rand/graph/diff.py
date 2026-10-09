"""Comparing two reference graphs (e.g. vanilla vs. an install modified by other mods)."""
from __future__ import annotations

from collections import Counter

from ds1rand.graph.model import Edge, Node, RefGraph


def _key(edge: Edge) -> tuple[Node, str, Node]:
    return edge.src, edge.field, edge.dst


def diff_edges(old: RefGraph, new: RefGraph) -> tuple[list[Edge], list[Edge]]:
    """Edges only in `new` (added) and only in `old` (removed), compared by source node, field and target node."""
    old_keys = {_key(e) for e in old.edges}
    new_keys = {_key(e) for e in new.edges}
    added = sorted({_key(e): e for e in new.edges if _key(e) not in old_keys}.values(), key=_key)
    removed = sorted({_key(e): e for e in old.edges if _key(e) not in new_keys}.values(), key=_key)
    return added, removed


def edge_group(edge: Edge) -> tuple[str, str, str]:
    """(source description, field, target param) for summarising edge changes."""
    src = edge.src.name if edge.src.kind == "param" else edge.src.kind
    dst = edge.dst.name if edge.dst.kind == "param" else edge.dst.kind
    return src, edge.field, dst


def summarise_edges(edges: list[Edge]) -> Counter:
    return Counter(edge_group(e) for e in edges)


def usage_changes(
    old: dict[Node, set[str]], new: dict[Node, set[str]]
) -> dict[Node, tuple[frozenset[str], frozenset[str]]]:
    """Param rows whose features differ: node -> (features before, features after)."""
    return {
        node: (frozenset(old.get(node, ())), frozenset(new.get(node, ())))
        for node in sorted(set(old) | set(new))
        if node.kind == "param" and old.get(node, set()) != new.get(node, set())
    }
