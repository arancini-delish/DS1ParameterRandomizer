"""Write a GameParam and item.msgbnd that route two spells through newly appended rows, to check in game that new rows
work when the game actually uses them (docs/AUDIT.md item 31). Output goes to `out/new_rows_test/`, never the game.

New rows (IDs from `ds1rand.catalogue.budget.IdAllocator`, the blocks the randomizer will use):
- Soul Arrow (Magic 3000) fires a new Bullet in the narrow block (Magic.refId is s16). That Bullet:
    looks like Great Heavy Soul Arrow (projectile and impact visuals of Bullet 3030),
    hits with a new AtkParam_Pc (wide block): Soul Arrow's attack with 10x magic damage,
    applies a new SpEffect (wide block) to the caster on cast: a copy of Heal (restores 300 HP).
- Magic Weapon (Magic 3100) applies a new SpEffect in the narrow block: Magic Weapon's buff lasting 300 s instead of
  60 s, with +400 magic damage instead of +80.
- The Sorcerer class starts with Magic Weapon as its second spell, so a new Sorcerer can test both at once.
- Both spells are renamed with a "[NEW ROWS]" prefix.

Usage: uv run python tools/make_new_rows_test.py [game_dir]
"""
import sys
from pathlib import Path

from ds1rand.baseline.compare import check_gameparam, check_item_text
from ds1rand.baseline.store import Baseline
from ds1rand.catalogue.budget import IdAllocator
from ds1rand.io.gameparam import GameParams
from ds1rand.io.install import GameInstall
from ds1rand.io.msg import ItemText

OUT_DIR = Path(__file__).resolve().parent.parent / "out" / "new_rows_test"
S16_MAX = 32767

SOUL_ARROW, MAGIC_WEAPON = 3000, 3100
GREAT_HEAVY_SOUL_ARROW_BULLET = 3030
HEAL_SPEFFECT = 1400
SORCERER = 3006


def main() -> None:
    install = GameInstall(Path(sys.argv[1])) if len(sys.argv) > 1 else GameInstall.default()
    install.validate()
    baseline = Baseline.load()
    for report in (check_gameparam(install.gameparam, baseline)[1], check_item_text(install.item_msgbnd, baseline)[1]):
        if report.diffs:
            raise SystemExit(f"Install is not vanilla, restore it first:\n{report.summary()}")

    params = GameParams.from_path(install.gameparam)
    ids = IdAllocator(baseline)

    # Soul Arrow -> new Bullet (narrow) -> new attack + new shooter SpEffect (wide).
    old_bullet = params.row_values("Magic", SOUL_ARROW)["refId"]
    old_attack = params.row_values("Bullet", old_bullet)["atkId_Bullet"]
    bullet = ids.allocate("Bullet", max_id=S16_MAX)
    attack = ids.allocate("AtkParam_Pc")
    heal = ids.allocate("SpEffectParam")
    params.add_row("AtkParam_Pc", attack, copy_from=old_attack)
    params.set_row_values("AtkParam_Pc", attack, {"atkMag": params.row_values("AtkParam_Pc", old_attack)["atkMag"] * 10})
    params.add_row("SpEffectParam", heal, copy_from=HEAL_SPEFFECT)
    params.add_row("Bullet", bullet, copy_from=old_bullet)
    visuals = params.row_values("Bullet", GREAT_HEAVY_SOUL_ARROW_BULLET)
    params.set_row_values("Bullet", bullet, {
        "atkId_Bullet": attack,
        "spEffectIDForShooter": heal,
        "sfxId_Bullet": visuals["sfxId_Bullet"],
        "sfxId_Hit": visuals["sfxId_Hit"],
    })
    params.set_row_values("Magic", SOUL_ARROW, {"refId": bullet})

    # Magic Weapon -> new SpEffect (narrow).
    old_buff = params.row_values("Magic", MAGIC_WEAPON)["refId"]
    buff = ids.allocate("SpEffectParam", max_id=S16_MAX)
    params.add_row("SpEffectParam", buff, copy_from=old_buff)
    params.set_row_values("SpEffectParam", buff, {"effectEndurance": 300.0, "magicAttackPower": 400})
    params.set_row_values("Magic", MAGIC_WEAPON, {"refId": buff})

    params.set_row_values("CharaInitParam", SORCERER, {"equip_Spell_02": MAGIC_WEAPON})
    changed = params.save(OUT_DIR / "param" / "GameParam" / "GameParam.parambnd.dcx")

    text = ItemText.from_path(install.item_msgbnd)
    for spell in (SOUL_ARROW, MAGIC_WEAPON):
        text.set("Magic_name", spell, f"[NEW ROWS] {text.get('Magic_name', spell)}")
    text.save(OUT_DIR / "msg" / "ENGLISH" / "item.msgbnd.dcx")

    print(f"Soul Arrow -> Bullet {bullet} (was {old_bullet}) -> AtkParam_Pc {attack}, shooter SpEffect {heal}")
    print(f"Magic Weapon -> SpEffect {buff} (was {old_buff})")
    print(f"Re-serialized params: {', '.join(changed)}")
    print(f"Wrote {OUT_DIR}")


if __name__ == "__main__":
    main()
