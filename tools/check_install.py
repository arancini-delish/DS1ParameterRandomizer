"""Compare an install's GameParam and item text against the vanilla baseline and print what differs.

Usage: uv run python tools/check_install.py [game_dir] [--rows]
"""
import argparse
from pathlib import Path

from ds1rand.baseline.compare import check_gameparam, check_item_text
from ds1rand.baseline.store import Baseline
from ds1rand.io.install import GameInstall


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_dir", nargs="?", type=Path)
    parser.add_argument("--rows", action="store_true", help="List every differing row/string")
    args = parser.parse_args()
    install = GameInstall(args.game_dir) if args.game_dir else GameInstall.default()
    install.validate()
    baseline = Baseline.load()

    _, param_report = check_gameparam(install.gameparam, baseline)
    print(param_report.summary())
    if args.rows:
        for diff in param_report.diffs:
            for row_id, fields in diff.changed.items():
                print(f"    {diff.name}[{row_id}]: " + ", ".join(f"{f} {b} -> {d}" for f, (b, d) in fields.items()))
            for row_id in diff.added:
                print(f"    {diff.name}[{row_id}]: added")
            for row_id in diff.removed:
                print(f"    {diff.name}[{row_id}]: removed")

    if not baseline.text:
        print("item.msgbnd.dcx: no text baseline yet")
        return
    _, text_report = check_item_text(install.item_msgbnd, baseline)
    print(text_report.summary())
    if args.rows:
        for diff in text_report.diffs:
            for text_id, (base, disk) in diff.changed.items():
                print(f"    {diff.stem}[{text_id}]: {base!r} -> {disk!r}")


if __name__ == "__main__":
    main()
