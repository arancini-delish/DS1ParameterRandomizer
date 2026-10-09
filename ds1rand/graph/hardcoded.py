"""Engine-hardcoded row references, curated in `data/catalogue/hardcoded.toml`."""
from __future__ import annotations

import tomllib
from pathlib import Path

from ds1rand.baseline.store import Baseline
from ds1rand.graph.model import CONFIDENCES, Edge, Node, RefGraph


def _expand(ids: list, existing: set[int]) -> list[int]:
    rows = []
    for item in ids:
        if isinstance(item, int):
            rows.append(item)
        else:
            first, last = (int(x) for x in item.split("-"))
            rows.extend(r for r in range(first, last + 1) if r in existing)
    return [r for r in rows if r in existing]


def add_hardcoded_edges(path: Path, baseline: Baseline, graph: RefGraph) -> None:
    entries = tomllib.loads(path.read_text(encoding="utf-8"))["entry"]
    for entry in entries:
        if entry["confidence"] not in CONFIDENCES or entry["param"] not in baseline.params:
            raise ValueError(f"Invalid hardcoded entry {entry['name']!r}")
        src = Node("engine", entry["name"], 0)
        for row_id in _expand(entry["ids"], set(baseline.params[entry["param"]].rows)):
            graph.add(Edge(src, Node.param(entry["param"], row_id), "hardcoded", "hardcoded", entry["confidence"]))
