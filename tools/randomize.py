"""Run ds1rand from the command line (the UI is `python -m ds1rand.ui`).

Builds on the files as the other mods left them (run item -> enemy -> fog gate first). By default writes to
out/randomized/ (mirroring the game folder: copy its `param` and `msg` folders over the game's, including the
`.ds1rand-base` / `.ds1rand.json` companions); `--in-place` writes into the game folder.

Settings come from a built-in preset (`--preset Standard`), a preset file (`--preset-file`), or a share string
(`--share`); `--rings PRESET` overrides the ring distribution, `--no-rings` / `--no-spells` /
`--no-projectiles` / `--no-enemies` turn a feature off.

Usage: uv run python tools/randomize.py [--preset NAME | --preset-file PATH | --share STRING] [--rings PRESET]
                                        [--no-rings] [--no-spells] [--no-projectiles]
                                        [--no-enemies] [--seed N] [--in-place] [--game-dir DIR] [--print-share]
"""
import argparse
from pathlib import Path

from ds1rand.features.rings import PRESETS as RING_PRESETS
from ds1rand.io.install import GameInstall
from ds1rand.presets.schema import BUILTIN, Preset
from ds1rand.run import DEFAULT_OUT, run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--preset", choices=sorted(BUILTIN), default="Standard")
    source.add_argument("--preset-file", type=Path)
    source.add_argument("--share")
    parser.add_argument("--rings", choices=sorted(RING_PRESETS), help="Ring tier distribution")
    parser.add_argument("--no-rings", action="store_true")
    parser.add_argument("--no-spells", action="store_true")
    parser.add_argument("--no-projectiles", action="store_true")
    parser.add_argument("--no-enemies", action="store_true")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--in-place", action="store_true", help="Write into the game folder")
    parser.add_argument("--game-dir")
    parser.add_argument("--print-share", action="store_true", help="Print the share string of the run")
    args = parser.parse_args()

    if args.share:
        preset = Preset.from_share_string(args.share)
    elif args.preset_file:
        preset = Preset.load(args.preset_file)
    else:
        preset = BUILTIN[args.preset]
    if args.rings:
        preset.rings.tier_weights = RING_PRESETS[args.rings]
    if args.no_rings:
        preset.rings.enabled = False
    if args.no_spells:
        preset.spells.enabled = False
    if args.no_projectiles:
        preset.projectiles.enabled = False
    if args.no_enemies:
        preset.enemies.enabled = False
    if args.seed is not None:
        preset.seed = args.seed

    install = GameInstall(Path(args.game_dir)) if args.game_dir else GameInstall.default()
    result = run(preset, install, out_dir=None if args.in_place else DEFAULT_OUT)
    for ring in result.rings:
        print(f"  {ring.ring_id} {result.ring_names.get(ring.ring_id, '?'):32} {ring.tier.name:9} "
              f"{', '.join(ring.summaries)}")
    if args.print_share:
        preset.seed = result.seed
        print(f"Share string: {preset.to_share_string()}")


if __name__ == "__main__":
    main()
