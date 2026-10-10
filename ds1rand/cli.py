"""Run ds1rand from the command line (the UI is `python -m ds1rand.ui` / `ds1rand.exe`).

Source checkout: `uv run python tools/randomize.py ...`; packaged build: `ds1rand-cli.exe ...`.

Builds on the files as the other mods left them (run item -> enemy -> fog gate first). By default writes to
out/randomized/ (mirroring the game folder: copy its `param` and `msg` folders over the game's, including the
`.ds1rand-base` / `.ds1rand.json` companions); `--in-place` writes into the game folder.

Settings come from a built-in preset (`--preset Standard`), a preset file (`--preset-file`), or a share string
(`--share`); `--rings PRESET` overrides the ring distribution, `--no-rings` / `--no-spells` /
`--no-projectiles` / `--no-enemies` /
`--no-weapons` / `--no-armor` /
`--no-appearance` turn a feature off.
A spoiler log (ds1rand-spoiler.txt) is written next to the output unless `--no-spoiler`.

Usage: ds1rand-cli [--preset NAME | --preset-file PATH | --share STRING] [--rings PRESET]
                                        [--no-rings] [--no-spells] [--no-projectiles]
                                        [--no-enemies] [--no-weapons] [--no-armor] [--no-appearance]
                                        [--seed N] [--in-place] [--game-dir DIR] [--print-share]
"""
import argparse
from pathlib import Path

from ds1rand import __version__
from ds1rand.features.rings import PRESETS as RING_PRESETS
from ds1rand.fingerprint import fingerprint
from ds1rand.io.install import GameInstall
from ds1rand.presets.schema import BUILTIN, Preset
from ds1rand.run import DEFAULT_OUT, run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"ds1rand {__version__}")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--preset", choices=sorted(BUILTIN), default="Standard")
    source.add_argument("--preset-file", type=Path)
    source.add_argument("--share")
    parser.add_argument("--rings", choices=sorted(RING_PRESETS), help="Ring tier distribution")
    parser.add_argument("--no-rings", action="store_true")
    parser.add_argument("--no-spells", action="store_true")
    parser.add_argument("--no-projectiles", action="store_true")
    parser.add_argument("--no-enemies", action="store_true")
    parser.add_argument("--no-weapons", action="store_true")
    parser.add_argument("--no-armor", action="store_true")
    parser.add_argument("--no-appearance", action="store_true")
    parser.add_argument("--no-spoiler", action="store_true", help="Do not write ds1rand-spoiler.txt")
    parser.add_argument("--fingerprint", action="store_true",
                        help="Print the game files fingerprint of the install (compare with co-op partners) and exit")
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
    if args.no_weapons:
        preset.weapons.enabled = False
    if args.no_armor:
        preset.armor.enabled = False
    if args.no_appearance:
        preset.appearance.enabled = False
    if args.seed is not None:
        preset.seed = args.seed

    install = GameInstall(Path(args.game_dir)) if args.game_dir else GameInstall.default()
    if args.fingerprint:
        print(fingerprint(install.root).text())
        return
    result = run(preset, install, out_dir=None if args.in_place else DEFAULT_OUT, spoiler=not args.no_spoiler)
    for ring in result.rings:
        print(f"  {ring.ring_id} {result.ring_names.get(ring.ring_id, '?'):32} {ring.tier.name:9} "
              f"{', '.join(ring.summaries)}")
    if args.print_share:
        preset.seed = result.seed
        print(f"Share string: {preset.to_share_string()}")


if __name__ == "__main__":
    main()
