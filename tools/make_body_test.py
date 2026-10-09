"""Write a GameParam that rewrites the character creation physique presets, to check in game which rows the physique
options read and whether saves keep the values (docs/AUDIT.md item 42). Output goes to `out/body_test/`, never the game.

CharaInitParam 2100-2108 and 2200-2208 hold the nine physiques' body scales (vanilla: Average 0, Slim -50, Very Slim
-100, Large +50, Very Large +100, Large Upper Body chest+arms, Large Lower Body abdomen+legs, Top-heavy head +100,
Tiny Head head -100). Starting class rows do not affect the body (tested: 3000-3009 / 2000-2009 had no effect).

Each physique option gets a different exaggeration. The 2100 rows make the part(s) huge, the 2200 rows make the same
part(s) tiny, so one look tells which row set an option (and sex) uses:

    Average           head          Large Upper Body  everything
    Slim              chest         Large Lower Body  head + arms
    Very Slim         abdomen       Top-heavy         chest + legs
    Large             arms          Tiny Head         abdomen + arms
    Very Large        legs

Builds on the installed files like a normal run (other mods' changes are kept; a previous ds1rand output is replaced).

Usage: uv run python tools/make_body_test.py [game_dir]
"""
import sys
from pathlib import Path

from ds1rand.io.install import GameInstall
from ds1rand.session import Session

OUT_DIR = Path(__file__).resolve().parent.parent / "out" / "body_test"
PARTS = ("Head", "Breast", "Abdomen", "Arm", "Leg")
PHYSIQUES = {
    "Average": ("Head",),
    "Slim": ("Breast",),
    "Very Slim": ("Abdomen",),
    "Large": ("Arm",),
    "Very Large": ("Leg",),
    "Large Upper Body": PARTS,
    "Large Lower Body": ("Head", "Arm"),
    "Top-heavy": ("Breast", "Leg"),
    "Tiny Head": ("Abdomen", "Arm"),
}
ROW_SETS = {2100: 100, 2200: -100}  # first row of each set -> value for the exaggerated parts


def main() -> None:
    install = GameInstall(Path(sys.argv[1])) if len(sys.argv) > 1 else GameInstall.default()
    install.validate()
    session = Session.open(install)
    rows = session.base.params["CharaInitParam"].rows
    for index, (name, parts) in enumerate(PHYSIQUES.items()):
        for first, value in ROW_SETS.items():
            if first + index in rows:
                session.store.set("CharaInitParam", first + index,
                                  {f"bodyScale{p}": value if p in parts else 0 for p in PARTS})
        print(f"  {name:17} {2100 + index} huge / {2200 + index} tiny: {', '.join(parts)}")
    written = session.write({"test": "physique body scales"}, out_dir=OUT_DIR)
    print(f"Wrote {', '.join(written)} to {OUT_DIR}")


if __name__ == "__main__":
    main()
