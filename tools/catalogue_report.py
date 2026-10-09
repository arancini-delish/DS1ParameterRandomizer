"""Report which features use each param's rows, and which rows are shared between features.

Usage: uv run python tools/catalogue_report.py [--shared PARAM]
"""
import argparse
from collections import Counter

from ds1rand.baseline.store import Baseline
from ds1rand.catalogue.usage import FEATURES, compute_usage
from ds1rand.graph.build import ORPHAN_PARAMS, build_graph


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shared", metavar="PARAM", help="List the shared rows of PARAM with their features")
    args = parser.parse_args()

    baseline = Baseline.load()
    usage = compute_usage(build_graph(baseline), baseline)

    print(f"{'param':22} {'rows':>5} {'used':>5} {'shared':>6}  " + " ".join(f"{f[:12]:>12}" for f in FEATURES))
    for param in ORPHAN_PARAMS:
        rows = [r for r in baseline.params[param].rows if r]
        tags = [features for node, features in usage.items() if node.name == param]
        per_feature = Counter(f for features in tags for f in features)
        shared = sum(len(features) > 1 for features in tags)
        print(f"{param:22} {len(rows):5} {len(tags):5} {shared:6}  " + " ".join(f"{per_feature[f]:12}" for f in FEATURES))

    if args.shared:
        combos = Counter()
        for node, features in sorted(usage.items()):
            if node.name == args.shared and len(features) > 1:
                combos[frozenset(features)] += 1
                print(f"  {node}: {', '.join(sorted(features))}")
        for combo, count in combos.most_common():
            print(f"{count:5}  {' + '.join(sorted(combo))}")


if __name__ == "__main__":
    main()
