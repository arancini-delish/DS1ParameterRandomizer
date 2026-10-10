"""Write variants of a run with groups of features turned off, to find which one breaks Seamless Co-op joining.

Output: `out/coop_bisect/<variant>/` (each mirrors the game folder: copy its `param` and `msg` folders over the
game's on every player's PC, then try joining). Variants:

    0_none                      no ds1rand changes: the game files as they were before ds1rand (the base)
    1_rings_spells_projectiles  SpEffects, bullets, attacks, throwables
    2_weapons_armor             equipment rows, NPC equipment copies (CharaInitParam)
    3_enemies_body_face         NpcParam / NpcThinkParam / MoveParam, FaceGenParam, physique rows (CharaInitParam)
    4_all                       everything (the normal run)

Every variant uses the same preset and seed, so a group behaves exactly as in the full run. `fingerprints.txt` lists
the params fingerprint each variant gives once installed: all players should see that code after copying it in.

Usage: uv run python tools/make_coop_bisect.py [--preset NAME] [--seed N] [--game-dir DIR]
"""
import argparse
import shutil
from pathlib import Path

from ds1rand.fingerprint import fingerprint
from ds1rand.io.install import GameInstall
from ds1rand.paths import APP_DIR
from ds1rand.presets.schema import BUILTIN, Preset
from ds1rand.run import run
from ds1rand.session import Session

OUT = APP_DIR / "out" / "coop_bisect"
FEATURES = ("rings", "spells", "projectiles", "enemies", "weapons", "armor", "appearance")
VARIANTS = {
    "1_rings_spells_projectiles": {"rings", "spells", "projectiles"},
    "2_weapons_armor": {"weapons", "armor"},
    "3_enemies_body_face": {"enemies", "appearance"},
    "4_all": set(FEATURES),
}


def _write_base(install: GameInstall, target: Path) -> None:
    """The files as they were before any ds1rand run (what ds1rand builds on)."""
    session = Session.open(install)
    for resolution, relative in ((session.gameparam_base, GameInstall.GAMEPARAM),
                                 (session.text_base, GameInstall.ITEM_MSGBND)):
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resolution.data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--preset", choices=sorted(BUILTIN), default="Standard")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--game-dir")
    args = parser.parse_args()
    install = GameInstall(Path(args.game_dir)) if args.game_dir else GameInstall.default()
    shutil.rmtree(OUT, ignore_errors=True)

    lines = []
    target = OUT / "0_none"
    _write_base(install, target)
    lines.append(f"0_none: {fingerprint(target).groups['params']}")
    for name, enabled in VARIANTS.items():
        preset = Preset.from_dict(BUILTIN[args.preset].to_dict())
        preset.seed = args.seed
        for feature in FEATURES:
            getattr(preset, feature).enabled = feature in enabled
        target = OUT / name
        run(preset, install, out_dir=target, log=lambda _: None)
        lines.append(f"{name}: {fingerprint(target).groups['params']}")
        print(f"Wrote {target}")
    (OUT / "fingerprints.txt").write_text(
        "Params fingerprint of each variant (the 'params' group code Validate shows once it is installed):\n"
        + "\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
