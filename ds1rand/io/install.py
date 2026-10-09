"""Locating the game files the randomizer reads and writes."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import ClassVar
from pathlib import Path

DEFAULT_GAME_DIR = Path(r"C:\Program Files (x86)\Steam\steamapps\common\DARK SOULS REMASTERED")
GAME_DIR_ENV_VAR = "DS1R_GAME_DIR"


@dataclass(frozen=True)
class GameInstall:
    """Paths inside a Dark Souls: Remastered install directory."""

    root: Path

    # Locations inside the game folder (also the layout of ds1rand output folders).
    GAMEPARAM: ClassVar[Path] = Path("param") / "GameParam" / "GameParam.parambnd.dcx"
    ITEM_MSGBND: ClassVar[Path] = Path("msg") / "ENGLISH" / "item.msgbnd.dcx"

    @property
    def gameparam(self) -> Path:
        return self.root / self.GAMEPARAM

    @property
    def item_msgbnd(self) -> Path:
        return self.root / self.ITEM_MSGBND

    def missing_files(self) -> list[Path]:
        return [p for p in (self.gameparam, self.item_msgbnd) if not p.is_file()]

    def validate(self) -> None:
        missing = self.missing_files()
        if missing:
            raise FileNotFoundError("Not a DSR install, missing: " + ", ".join(str(p) for p in missing))

    @classmethod
    def default(cls) -> GameInstall:
        """Install from the `DS1R_GAME_DIR` environment variable, else the default Steam location."""
        return cls(Path(os.environ.get(GAME_DIR_ENV_VAR, DEFAULT_GAME_DIR)))
