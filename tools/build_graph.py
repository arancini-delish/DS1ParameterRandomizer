"""Build the reference graph, print a summary, and write it to `out/graph.json` for inspection.

With `--extract`, first re-extract the external sources (EMEVD, MSB, TAE, AI Lua) from vanilla files into `data/catalogue/`. If other
mods have modified the install, `--prefer-bak` reads their `<file>.bak` backups instead (check those are vanilla).

Usage: uv run python tools/build_graph.py [--extract [game_dir] [--prefer-bak]] [--unresolved] [--orphans]
"""
import argparse
from collections import Counter
from pathlib import Path

from ds1rand.baseline.store import Baseline
from ds1rand.graph.build import build_graph, extract_external, orphans
from ds1rand.io.install import GameInstall

OUT = Path(__file__).resolve().parent.parent / "out" / "graph.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", nargs="?", const="", metavar="GAME_DIR",
                        help="Re-extract external sources from a vanilla install (default: DS1R_GAME_DIR / Steam)")
    parser.add_argument("--prefer-bak", action="store_true", help="With --extract, read <file>.bak where present")
    parser.add_argument("--unresolved", action="store_true", help="List every unresolved reference")
    parser.add_argument("--orphans", action="store_true", help="List rows nothing references (dead or uncatalogued)")
    args = parser.parse_args()

    baseline = Baseline.load()
    if args.extract is not None:
        install = GameInstall(Path(args.extract)) if args.extract else GameInstall.default()
        install.validate()
        for file_name, graph in extract_external(install, baseline, prefer_bak=args.prefer_bak).items():
            print(f"Extracted {file_name}: {len(graph.edges)} edges, {len(graph.unresolved)} unresolved")

    graph = build_graph(baseline)
    graph.write(OUT)

    print(f"{len(graph.edges)} edges, {len(graph.nodes)} nodes, {len(graph.unresolved)} unresolved -> {OUT}")
    print("Edges by source and confidence:")
    for (source, confidence), count in sorted(Counter((e.source, e.confidence) for e in graph.edges).items()):
        print(f"  {source:20} {confidence:10} {count}")
    print("Unresolved by field:")
    for (kind, param, field, reason), count in Counter(
        (u.src.kind, u.src.name if u.src.kind == "param" else "*", u.field, u.reason) for u in graph.unresolved
    ).most_common():
        print(f"  {count:5}  {kind}:{param}.{field}: {reason}")
    print("Unreferenced rows (dead data or engine use not yet catalogued):")
    for param, rows in orphans(graph, baseline).items():
        print(f"  {param:22} {len(rows):5}" + (f"  {rows}" if args.orphans else ""))
    if args.unresolved:
        for u in graph.unresolved:
            print(f"  {u.src}.{u.field} = {u.value} -> {', '.join(u.targets)}: {u.reason}")


if __name__ == "__main__":
    main()
