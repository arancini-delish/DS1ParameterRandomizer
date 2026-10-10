"""Which particle effects (FFX) are loaded where (docs/AUDIT.md item 18).

Bullet visuals (`sfxId_Bullet`, `sfxId_Hit`, `sfxId_Flick`) are FFX IDs. The game loads `sfx/*.ffxbnd.dcx` bundles:
    FRPG_SfxBnd_CommonEffects, FRPG_SfxBnd_Patch    always (player effects, shared enemy effects)
    FRPG_SfxBnd_mXX, FRPG_SfxBnd_mXX_YY             with map mXX_YY_00_00 (area bundle + map bundle)
    FRPG_SfxBnd_cXXXX                               with character cXXXX (a few DLC characters)
An effect that is not loaded is simply not drawn: the bullet still flies and hits, invisibly. The bundles are read from
the install, so effects other mods add (the enemy randomizer copies enemy effects into CommonEffects) count.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from soulstruct.containers import Binder

ALWAYS = ("CommonEffects", "Patch")
_BUNDLE = re.compile(r"^FRPG_SfxBnd_(\w+)\.ffxbnd\.dcx$", re.IGNORECASE)
_FFX = re.compile(r"f(\d+)\.ffx$", re.IGNORECASE)
SFX_FIELDS = ("sfxId_Bullet", "sfxId_Hit", "sfxId_Flick")


@dataclass(frozen=True)
class EffectResidency:
    always: frozenset[int]
    bundles: dict[str, frozenset[int]]  # "m10", "m10_00", "c4500" -> FFX IDs

    @classmethod
    def from_sfx_dir(cls, sfx_dir: Path) -> EffectResidency:
        logging.getLogger("soulstruct").setLevel(logging.ERROR)
        bundles = {}
        for path in sorted(sfx_dir.glob("*.ffxbnd.dcx")):
            match = _BUNDLE.match(path.name)
            if match:
                binder = Binder.from_path(path)
                bundles[match.group(1)] = frozenset(
                    int(m.group(1)) for e in binder.entries if (m := _FFX.search(e.name)))
        always = frozenset().union(*(ids for name, ids in bundles.items() if name in ALWAYS))
        return cls(always, {name: ids for name, ids in bundles.items() if name not in ALWAYS})

    def loaded(self, maps: Iterable[str] = (), models: Iterable[str] = ()) -> frozenset[int]:
        """Effects loaded everywhere in `maps` (map stems like "m10_00_00_00"); with no maps, only the always-loaded
        ones. Character bundles of `models` are added."""
        loaded = None
        for stem in set(maps):
            parts = stem.split("_")
            here = self.bundles.get(parts[0], frozenset()) | self.bundles.get("_".join(parts[:2]), frozenset())
            loaded = here if loaded is None else loaded & here
        extra = frozenset().union(*(self.bundles.get(m, frozenset()) for m in models))
        return self.always | (loaded or frozenset()) | extra


def bullet_effects(values: dict) -> set[int]:
    return {values[f] for f in SFX_FIELDS if values[f] > 0}
