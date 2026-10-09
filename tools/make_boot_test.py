"""Write a GameParam and item.msgbnd with obvious, harmless edits, to check the game boots with files we wrote.

Output goes to `out/boot_test/` (never the game folder). Edits:
- Darksign and every Estus Flask are renamed with a "[TEST]" prefix; the Darksign summary is replaced.
- Every weapon weighs 0.1 (EquipParamWeapon is re-serialized by soulstruct).
- A copy of an existing Bullet row is appended under a new ID (checks the game accepts appended rows).

Usage: uv run python tools/make_boot_test.py [game_dir]
"""
import sys
from pathlib import Path

from ds1rand.io.gameparam import GameParams
from ds1rand.io.install import GameInstall
from ds1rand.io.msg import ItemText

OUT_DIR = Path(__file__).resolve().parent.parent / "out" / "boot_test"
DARKSIGN_ID = 117
ESTUS_IDS = range(200, 216)


def main() -> None:
    install = GameInstall(Path(sys.argv[1])) if len(sys.argv) > 1 else GameInstall.default()
    install.validate()

    params = GameParams.from_path(install.gameparam)
    for row in params["EquipParamWeapon"].values():
        row["weight"] = 0.1
    source_bullet = next(iter(params["Bullet"].rows))
    new_bullet = params.next_free_id("Bullet", 900_000)
    params.add_row("Bullet", new_bullet, copy_from=source_bullet)
    changed = params.save(OUT_DIR / "param" / "GameParam" / "GameParam.parambnd.dcx")

    text = ItemText.from_path(install.item_msgbnd)
    for item_id in (DARKSIGN_ID, *ESTUS_IDS):
        if name := text.get("Item_name", item_id):
            text.set("Item_name", item_id, f"[TEST] {name}")
    text.set("Item_description", DARKSIGN_ID, "Boot test: written by ds1rand")
    text.save(OUT_DIR / "msg" / "ENGLISH" / "item.msgbnd.dcx")

    print(f"Re-serialized params: {', '.join(changed)} (appended Bullet {new_bullet})")
    print(f"Wrote {OUT_DIR}; copy its param/ and msg/ folders over the game's, after backing up the originals.")


if __name__ == "__main__":
    main()
