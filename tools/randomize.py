"""Run ds1rand's randomizers on an install (until the UI exists).

Builds on the files as the other mods left them (run item -> enemy -> fog gate first). By default writes the result to
out/randomized/ (mirroring the game folder: copy its `param` and `msg` folders over the game's); `--in-place` writes
into the game folder directly, keeping `<file>.ds1rand-base` copies and markers so re-runs start from the same base.

Usage: uv run python tools/randomize.py --rings [PRESET] [--seed N] [--no-isolate-npcs] [--in-place] [--game-dir DIR]
"""
import argparse
import random
from pathlib import Path

from ds1rand.features.rings import PRESETS, RingConfig, randomize_rings
from ds1rand.io.install import GameInstall
from ds1rand.session import Session

OUT = Path(__file__).resolve().parent.parent / "out" / "randomized"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rings", nargs="?", const="Standard", choices=sorted(PRESETS), help="Randomize rings")
    parser.add_argument("--no-isolate-npcs", action="store_true", help="Let NPC phantoms share randomized rings")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--in-place", action="store_true", help="Write into the game folder")
    parser.add_argument("--game-dir")
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else random.randrange(2**31)
    rng = random.Random(seed)
    session = Session.open(GameInstall(Path(args.game_dir)) if args.game_dir else None)
    print(f"Seed {seed}. GameParam base: {session.gameparam_base.state}; item text base: {session.text_base.state}")
    for conflict in session.conflicts:
        print(f"  conflict: {conflict}")
    foreign = [d.summary() for d in session.foreign_changes()["params"]]
    if foreign:
        print("Other mods' changes kept: " + "; ".join(foreign))

    info = {"seed": seed}
    if args.rings:
        config = RingConfig(tier_weights=PRESETS[args.rings], isolate_npcs=not args.no_isolate_npcs)
        results = randomize_rings(session, config, rng)
        info["rings"] = args.rings
        print(f"\nRings ({args.rings}):")
        for r in results:
            name = session.base.text.get(13, ("", {}))[1].get(r.ring_id, "?")
            print(f"  {r.ring_id} {name:32} {r.tier.name:9} {', '.join(r.summaries)}")

    written = session.write(info, out_dir=None if args.in_place else OUT)
    target = session.install.root if args.in_place else OUT
    print(f"\nWrote {', '.join(written) or 'nothing'} to {target}")


if __name__ == "__main__":
    main()
