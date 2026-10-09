"""Build `data/baseline/` from vanilla game files.

The inputs must be vanilla DSR files. Other tools (item/enemy randomizers, Paramdomizer) modify these files in place, and
their `.bak` copies are only vanilla if no other tool ran first, so check what you point this at.

Usage:
    uv run python tools/build_baseline.py --gameparam PATH --item-msgbnd PATH [--exe PATH] [--out DIR]
Omitted paths default to the install (DS1R_GAME_DIR or the default Steam path).
"""
import argparse
from pathlib import Path

from ds1rand.baseline.store import DEFAULT_BASELINE_DIR, Baseline, sha256_file
from ds1rand.io.gameparam import GameParams
from ds1rand.io.install import GameInstall
from ds1rand.io.msg import ItemText


def main() -> None:
    install = GameInstall.default()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gameparam", type=Path, default=install.gameparam)
    parser.add_argument("--item-msgbnd", type=Path, default=install.item_msgbnd)
    parser.add_argument("--exe", type=Path, default=install.root / "DarkSoulsRemastered.exe")
    parser.add_argument("--params-only", action="store_true", help="Skip item text (keeps any existing text baseline)")
    parser.add_argument("--out", type=Path, default=DEFAULT_BASELINE_DIR)
    args = parser.parse_args()

    sources = {"GameParam.parambnd.dcx": sha256_file(args.gameparam)}
    text = None
    if not args.params_only:
        sources["item.msgbnd.dcx"] = sha256_file(args.item_msgbnd)
        text = ItemText.from_path(args.item_msgbnd)
    if args.exe.is_file():
        sources["DarkSoulsRemastered.exe"] = sha256_file(args.exe)

    baseline = Baseline.from_game_files(GameParams.from_path(args.gameparam), text, sources)
    if args.params_only and (args.out / "manifest.json").is_file():
        previous = Baseline.load(args.out)
        baseline.text = previous.text
        baseline.manifest["text"] = previous.manifest.get("text", [])
        if "item.msgbnd.dcx" in previous.manifest["sources"]:
            baseline.manifest["sources"]["item.msgbnd.dcx"] = previous.manifest["sources"]["item.msgbnd.dcx"]
    baseline.write(args.out)

    rows = sum(info["rows"] for info in baseline.manifest["params"].values())
    print(f"Wrote {args.out}: {len(baseline.params)} params, {rows} rows, {len(baseline.text)} FMGs")
    for name, sha in baseline.manifest["sources"].items():
        print(f"  {name}: {sha}")


if __name__ == "__main__":
    main()
