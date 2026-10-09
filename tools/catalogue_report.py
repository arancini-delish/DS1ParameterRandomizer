"""Report which features use each param's rows, which rows are shared between features, and subtype coverage.

Usage: uv run python tools/catalogue_report.py [--shared PARAM] [--cap N]
"""
import argparse
from collections import Counter

from ds1rand.baseline.store import Baseline
from ds1rand.catalogue.budget import RowBudget, param_budgets
from ds1rand.catalogue.effects import EffectClassifier
from ds1rand.catalogue.subtypes import coverage
from ds1rand.catalogue.usage import FEATURES, compute_usage
from ds1rand.graph.build import ORPHAN_PARAMS, build_graph


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shared", metavar="PARAM", help="List the shared rows of PARAM with their features")
    parser.add_argument("--cap", type=int, default=None, help="New-row cap per param for the budget (default: none)")
    args = parser.parse_args()

    baseline = Baseline.load()
    graph = build_graph(baseline)
    usage = compute_usage(graph, baseline)

    print(f"{'param':22} {'rows':>5} {'used':>5} {'shared':>6}  " + " ".join(f"{f[:12]:>12}" for f in FEATURES))
    for param in ORPHAN_PARAMS:
        rows = [r for r in baseline.params[param].rows if r]
        tags = [features for node, features in usage.items() if node.name == param]
        per_feature = Counter(f for features in tags for f in features)
        shared = sum(len(features) > 1 for features in tags)
        print(f"{param:22} {len(rows):5} {len(tags):5} {shared:6}  " + " ".join(f"{per_feature[f]:12}" for f in FEATURES))

    used = {p: sorted(n.id for n in usage if n.name == p) for p in ("Bullet", "Magic")}
    for param, counts in coverage(baseline, used).items():
        print(f"\n{param} subtypes ({sum(counts.values())} used rows):")
        for subtype, count in counts.most_common():
            print(f"  {count:5}  {subtype}")

    effects = EffectClassifier(baseline, graph)
    speffects = Counter(effects.speffect(r).subtype for r in baseline.params["SpEffectParam"].rows if r)
    print(f"\nSpEffectParam subtypes ({sum(speffects.values())} rows):")
    for subtype, count in speffects.most_common():
        print(f"  {count:5}  {subtype}")
    for param in ("AtkParam_Pc", "AtkParam_Npc"):
        attacks = Counter(effects.attack(param, r) for r in baseline.params[param].rows if r)
        print(f"\n{param} subtypes ({sum(attacks.values())} rows):")
        for subtype, count in attacks.most_common():
            print(f"  {count:5}  {subtype}")

    budgets = param_budgets(graph, baseline)
    plan = RowBudget(default=args.cap).plan(budgets)
    print(f"\nRow budget (cap per param: {'none' if args.cap is None else args.cap}):")
    print(f"  {'param':20} {'used':>5} {'copies':>6} {'coupled':>7} {'surplus':>7} {'short':>5}  coupled features")
    for param, budget in budgets.items():
        surplus = plan[param]["surplus"]
        coupled = ", ".join(f"{'+'.join(sorted(g))} {n}" for g, n in budget.coupled_groups.most_common(3))
        print(f"  {param:20} {budget.used:5} {budget.copies_needed:6} {budget.coupled_rows:7} "
              f"{'-' if surplus is None else surplus:>7} {plan[param]['shortfall']:5}  {coupled}")

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
