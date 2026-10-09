"""The static reference graph: which rows (and, in later stages, which game files) reference which rows.

Nodes are `Node(kind, name, id)`. Param rows are kind "param" with the param name and row ID (e.g. `Bullet:100`);
later sources add kinds like "emevd", "msb" and "tae". Edges point from the referencing node to the referenced node and
record the referencing field, the extractor that found them, and a confidence:
    certain    the target is unambiguous
    ambiguous  the field could mean several targets (e.g. a Bullet's attack ID is a player or NPC attack depending on who
               fires it) and every existing candidate got an edge
    inferred   derived from a rule not yet confirmed against the game (see `docs/AUDIT.md`)
References that could not be resolved (e.g. to a missing row) are kept in `unresolved` for the audit.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

CONFIDENCES = ("certain", "ambiguous", "inferred")


@dataclass(frozen=True, slots=True, order=True)
class Node:
    kind: str
    name: str
    id: int

    @classmethod
    def param(cls, name: str, row_id: int) -> Node:
        return cls("param", name, row_id)

    def __str__(self) -> str:
        return f"{self.name}:{self.id}" if self.kind == "param" else f"{self.kind}/{self.name}:{self.id}"


@dataclass(frozen=True, slots=True)
class Edge:
    src: Node
    dst: Node
    field: str
    source: str  # extractor, e.g. "meta", "soulstruct", "behavior_variation"
    confidence: str = "certain"


@dataclass(frozen=True, slots=True)
class Unresolved:
    src: Node
    field: str
    value: int
    targets: tuple[str, ...]  # params the value was looked up in
    reason: str


@dataclass
class RefGraph:
    edges: list[Edge] = field(default_factory=list)
    unresolved: list[Unresolved] = field(default_factory=list)

    def __post_init__(self):
        self._out: dict[Node, list[Edge]] = defaultdict(list)
        self._in: dict[Node, list[Edge]] = defaultdict(list)
        for edge in self.edges:
            self._index(edge)

    def _index(self, edge: Edge) -> None:
        self._out[edge.src].append(edge)
        self._in[edge.dst].append(edge)

    def add(self, edge: Edge) -> None:
        self.edges.append(edge)
        self._index(edge)

    @property
    def nodes(self) -> set[Node]:
        return set(self._out) | set(self._in)

    def refs_of(self, node: Node) -> list[Edge]:
        """Edges from `node` to the nodes it references."""
        return self._out.get(node, [])

    def users_of(self, node: Node) -> list[Edge]:
        """Edges into `node` from the nodes that reference it."""
        return self._in.get(node, [])

    def reach(self, node: Node, confidences: Iterable[str] = CONFIDENCES) -> set[Node]:
        """Every node transitively referenced by `node` (excluding itself unless in a cycle)."""
        return self._walk(node, self._out, "dst", set(confidences))

    def reached_by(self, node: Node, confidences: Iterable[str] = CONFIDENCES) -> set[Node]:
        """Every node that transitively references `node`."""
        return self._walk(node, self._in, "src", set(confidences))

    @staticmethod
    def _walk(start: Node, index: dict[Node, list[Edge]], end: str, confidences: set[str]) -> set[Node]:
        seen: set[Node] = set()
        stack = [start]
        while stack:
            for edge in index.get(stack.pop(), []):
                nxt = getattr(edge, end)
                if edge.confidence in confidences and nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    def param_nodes(self, name: str) -> Iterator[Node]:
        return (n for n in self.nodes if n.kind == "param" and n.name == name)

    # Serialization: compact arrays, one edge per line, so `data/catalogue/graph.json` diffs per edge.

    def write(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        edges = sorted(self.edges, key=lambda e: (e.src, e.field, e.dst, e.source))
        edge_lines = [json.dumps([*_node_list(e.src), e.field, *_node_list(e.dst), e.source, e.confidence]) for e in edges]
        unresolved = sorted(self.unresolved, key=lambda u: (u.src, u.field))
        unresolved_lines = [
            json.dumps([*_node_list(u.src), u.field, u.value, list(u.targets), u.reason]) for u in unresolved
        ]
        path.write_text(
            '{"edges": [\n' + ",\n".join(edge_lines) + '\n],\n"unresolved": [\n' + ",\n".join(unresolved_lines) + "\n]}\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path | str) -> RefGraph:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        edges = [Edge(Node(*e[0:3]), Node(*e[4:7]), e[3], e[7], e[8]) for e in data["edges"]]
        unresolved = [Unresolved(Node(*u[0:3]), u[3], u[4], tuple(u[5]), u[6]) for u in data["unresolved"]]
        return cls(edges, unresolved)


def _node_list(node: Node) -> list:
    return [node.kind, node.name, node.id]
