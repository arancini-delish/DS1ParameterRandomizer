"""Write a GameParam that gives every starting class an exaggerated body, to check in game whether character creation
reads the class rows' body scales (docs/AUDIT.md item 42). Output goes to `out/body_test/`, never the game.

Builds on the installed files like a normal run (other mods' changes are kept; a previous ds1rand output is replaced),
so copy `param` over the game's and start a new game. Both class row sets get the same values (3000-3009, and the
2000-2009 rows of unknown purpose), so whichever one character creation reads shows up. Each class exaggerates one
body part, so the result shows which part each field drives:

    Warrior    huge head        Knight     huge chest       Wanderer   huge abdomen
    Thief      huge arms        Bandit     huge legs        Hunter     everything tiny
    Sorcerer   tiny head        Pyromancer everything huge  Cleric     tiny legs
    Deprived   tiny arms

What to look at: the class preview in character creation, the body after picking a class (and physique), and the
character once in game. Running the randomizer afterwards replaces this output.

Usage: uv run python tools/make_body_test.py [game_dir]
"""
import sys
from pathlib import Path

from ds1rand.io.install import GameInstall
from ds1rand.session import Session

OUT_DIR = Path(__file__).resolve().parent.parent / "out" / "body_test"
PARTS = ("Head", "Breast", "Abdomen", "Arm", "Leg")
CLASSES = {
    "Warrior": {"Head": 100},
    "Knight": {"Breast": 100},
    "Wanderer": {"Abdomen": 100},
    "Thief": {"Arm": 100},
    "Bandit": {"Leg": 100},
    "Hunter": dict.fromkeys(PARTS, -100),
    "Sorcerer": {"Head": -100},
    "Pyromancer": dict.fromkeys(PARTS, 100),
    "Cleric": {"Leg": -100},
    "Deprived": {"Arm": -100},
}


def main() -> None:
    install = GameInstall(Path(sys.argv[1])) if len(sys.argv) > 1 else GameInstall.default()
    install.validate()
    session = Session.open(install)
    for index, (name, scales) in enumerate(CLASSES.items()):
        values = {f"bodyScale{part}": scales.get(part, 0) for part in PARTS}
        for row in (3000 + index, 2000 + index):
            if row in session.base.params["CharaInitParam"].rows:
                session.store.set("CharaInitParam", row, values)
        print(f"  {name:11} {3000 + index} / {2000 + index}: "
              f"{', '.join(f'{p} {v:+d}' for p, v in scales.items())}")
    written = session.write({"test": "body scales"}, out_dir=OUT_DIR)
    print(f"Wrote {', '.join(written)} to {OUT_DIR}")


if __name__ == "__main__":
    main()
