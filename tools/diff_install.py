"""Find out exactly what other mods (item / enemy / fog gate randomizers) change in an install.

Commands:
    snapshot NAME [--game-dir DIR]   hash every file in the install to out/install_snapshots/NAME.json
    files A B                        files added, removed and changed between snapshots A and B
    report NAME [--game-dir DIR]     compare the installed game with the vanilla baseline and catalogue; writes
                                     out/install_reports/NAME.md

`report` covers: GameParam rows and fields, item text, which event/map/animation/AI files differ from the recorded
vanilla files, the reference graph built from the installed files vs. the vanilla graph (links added and removed per
source and field), rows whose using features changed (e.g. a Bullet an enemy now fires), and changed rows in the params
the randomizers edit.

Suggested use: Steam-verify, `snapshot vanilla`; run one mod, `snapshot item`, `files vanilla item`, `report item`;
verify again before the next mod; finally run all mods in order (item -> enemy -> fog gate) and report again.
"""
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS = ROOT / "out" / "install_snapshots"
REPORTS = ROOT / "out" / "install_reports"
SAMPLES = 8
EDITED_PARAMS = ("Magic", "Bullet", "AtkParam_Pc", "AtkParam_Npc", "SpEffectParam", "BehaviorParam",
                 "BehaviorParam_PC", "EquipParamAccessory", "EquipParamWeapon", "EquipParamGoods", "NpcParam",
                 "NpcThinkParam", "MoveParam")


def _install(game_dir: str | None):
    from ds1rand.io.install import GameInstall

    install = GameInstall(Path(game_dir)) if game_dir else GameInstall.default()
    install.validate()
    return install


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(name: str, game_dir: str | None) -> None:
    install = _install(game_dir)
    files = {}
    for path in sorted(p for p in install.root.rglob("*") if p.is_file()):
        files[path.relative_to(install.root).as_posix()] = {"size": path.stat().st_size, "sha256": _sha256(path)}
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    out = SNAPSHOTS / f"{name}.json"
    out.write_text(json.dumps({"root": str(install.root), "files": files}, indent=1), encoding="utf-8")
    print(f"{len(files)} files -> {out}")


def compare_files(a: str, b: str) -> None:
    old = json.loads((SNAPSHOTS / f"{a}.json").read_text(encoding="utf-8"))["files"]
    new = json.loads((SNAPSHOTS / f"{b}.json").read_text(encoding="utf-8"))["files"]
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(f for f in set(old) & set(new) if old[f]["sha256"] != new[f]["sha256"])
    for title, paths in (("Added", added), ("Removed", removed), ("Changed", changed)):
        by_dir = Counter(p.split("/")[0] if "/" in p else "." for p in paths)
        print(f"{title}: {len(paths)} files ({', '.join(f'{d} {n}' for d, n in by_dir.most_common())})")
        for path in paths:
            print(f"  {path}")


def report(name: str, game_dir: str | None) -> None:
    from ds1rand.baseline.compare import check_gameparam, check_item_text
    from ds1rand.baseline.store import Baseline
    from ds1rand.catalogue.usage import compute_usage
    from ds1rand.graph.build import CATALOGUE_DIR, SOURCES_FILE, build_graph, build_install_graph, source_files, source_hashes
    from ds1rand.graph.diff import diff_edges, summarise_edges, usage_changes

    install = _install(game_dir)
    baseline = Baseline.load()
    lines = [f"# Install report: {name}", "", f"Install: `{install.root}`", ""]

    print("Comparing GameParam and item text...")
    _, param_report = check_gameparam(install.gameparam, baseline)
    _, text_report = check_item_text(install.item_msgbnd, baseline)
    lines += ["## GameParam", "", f"State: **{param_report.state.value}**", ""]
    if param_report.diffs:
        lines += ["| Param | Changed | Added | Removed | Fields changed (rows) |", "|---|---|---|---|---|"]
        for diff in param_report.diffs:
            fields = Counter(f for row in diff.changed.values() for f in row)
            top = ", ".join(f"{f} ({n})" for f, n in fields.most_common(6)) + (" ..." if len(fields) > 6 else "")
            lines.append(f"| {diff.name} | {len(diff.changed)} | {len(diff.added)} | {len(diff.removed)} | {top} |")
        lines.append("")
    lines += ["## Item text", "", f"State: **{text_report.state.value}**", ""]
    lines += [f"- {d.stem} (FMG {d.fmg_id}): {len(d.changed)} strings" for d in text_report.diffs] + [""]

    recorded = json.loads((CATALOGUE_DIR / SOURCES_FILE).read_text(encoding="utf-8"))
    live = source_hashes(source_files(install))
    lines += ["## Event, map, animation and AI files", ""]
    for source, files in recorded.items():
        differ = sorted(s for s, entry in files.items() if live[source].get(s, {}).get("sha256") != entry["sha256"])
        new = sorted(set(live[source]) - set(files))
        lines.append(f"- {source}: {len(differ)} of {len(files)} differ from vanilla"
                     + (f" ({', '.join(differ)})" if differ else "") + (f"; new files: {', '.join(new)}" if new else ""))
    lines.append("")

    print("Building the vanilla and installed reference graphs...")
    vanilla_graph = build_graph(baseline)
    installed, installed_graph = build_install_graph(install)
    added, removed = diff_edges(vanilla_graph, installed_graph)
    lines += ["## Reference links", "", f"{len(added)} links added, {len(removed)} removed (installed vs vanilla).", ""]
    for title, edges in (("Added", added), ("Removed", removed)):
        if not edges:
            continue
        lines += [f"### {title}", "", "| From | Field | To | Links | Examples |", "|---|---|---|---|---|"]
        examples = defaultdict(list)
        for e in edges:
            key = (e.src.name if e.src.kind == "param" else e.src.kind, e.field,
                   e.dst.name if e.dst.kind == "param" else e.dst.kind)
            if len(examples[key]) < 3:
                examples[key].append(f"{e.src} -> {e.dst}")
        for (src, field, dst), count in summarise_edges(edges).most_common():
            lines.append(f"| {src} | {field} | {dst} | {count} | {'; '.join(examples[(src, field, dst)])} |")
        lines.append("")

    print("Comparing which features use each row...")
    changes = usage_changes(compute_usage(vanilla_graph, baseline), compute_usage(installed_graph, installed))
    lines += ["## Rows whose using features changed", ""]
    by_param = defaultdict(list)
    for node, (before, after) in changes.items():
        by_param[node.name].append((node, before, after))
    if by_param:
        lines += ["| Param | Rows | Examples (before -> after) |", "|---|---|---|"]
        for param, rows in sorted(by_param.items(), key=lambda x: -len(x[1])):
            examples = "; ".join(f"{n.id}: {'+'.join(sorted(b)) or '-'} -> {'+'.join(sorted(a)) or '-'}"
                                 for n, b, a in rows[:SAMPLES])
            lines.append(f"| {param} | {len(rows)} | {examples} |")
    else:
        lines.append("None.")
    lines.append("")

    lines += ["## Overlap with params the randomizers edit", ""]
    overlap = [d for d in param_report.diffs if d.name in EDITED_PARAMS]
    if overlap:
        for diff in overlap:
            rows = sorted(diff.changed)[:SAMPLES * 2]
            lines.append(f"- **{diff.name}**: {len(diff.changed)} changed {rows}{' ...' if len(diff.changed) > len(rows) else ''}, "
                         f"{len(diff.added)} added {diff.added[:SAMPLES]}, {len(diff.removed)} removed {diff.removed[:SAMPLES]}")
    else:
        lines.append("None: no changed rows in the params the randomizers edit.")
    lines.append("")

    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"{name}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("snapshot")
    p.add_argument("name")
    p.add_argument("--game-dir")
    p = commands.add_parser("files")
    p.add_argument("a")
    p.add_argument("b")
    p = commands.add_parser("report")
    p.add_argument("name")
    p.add_argument("--game-dir")
    args = parser.parse_args()
    if args.command == "snapshot":
        snapshot(args.name, args.game_dir)
    elif args.command == "files":
        compare_files(args.a, args.b)
    else:
        report(args.name, args.game_dir)


if __name__ == "__main__":
    main()
