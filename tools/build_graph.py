"""Build the reference graph from the vanilla baseline, print a summary, and write it to `out/graph.json`.

The graph is derived data: code builds it from `data/baseline` on demand, so the JSON is only for inspection.

Usage: uv run python tools/build_graph.py [--unresolved]
"""
import argparse
from collections import Counter
from pathlib import Path

from ds1rand.baseline.store import Baseline
from ds1rand.graph.params import extract_param_edges

OUT = Path(__file__).resolve().parent.parent / "out" / "graph.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unresolved", action="store_true", help="List every unresolved reference")
    args = parser.parse_args()

    graph = extract_param_edges(Baseline.load())
    graph.write(OUT)

    print(f"{len(graph.edges)} edges, {len(graph.nodes)} nodes, {len(graph.unresolved)} unresolved -> {OUT}")
    print("Edges by source and confidence:")
    for (source, confidence), count in sorted(Counter((e.source, e.confidence) for e in graph.edges).items()):
        print(f"  {source:20} {confidence:10} {count}")
    print("Unresolved by field:")
    for (param, field, reason), count in Counter(
        (u.src.name, u.field, u.reason) for u in graph.unresolved
    ).most_common():
        print(f"  {count:5}  {param}.{field}: {reason}")
    if args.unresolved:
        for u in graph.unresolved:
            print(f"  {u.src}.{u.field} = {u.value} -> {', '.join(u.targets)}: {u.reason}")


if __name__ == "__main__":
    main()
