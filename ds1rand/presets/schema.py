"""Presets: every setting of a run, versioned, as JSON files or a short share string.

A preset holds one section per feature (rings, spells, projectiles, enemies, weapons, armor) plus the
seed. Share strings are "DS1R" + version + "-" + base64url(zlib(JSON)), so pasting one reproduces a run exactly.
Unknown keys are ignored and missing keys take defaults, so presets from older versions keep loading.
"""
from __future__ import annotations

import base64
import json
import zlib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from ds1rand.features.armor import PRESETS as ARMOR_PRESETS
from ds1rand.features.enemies import PRESETS as ENEMY_PRESETS
from ds1rand.features.rings import PRESETS as RING_PRESETS
from ds1rand.features.projectiles import ENEMY_PRESETS as ENEMY_PROJECTILE_PRESETS
from ds1rand.features.projectiles import PRESETS as PROJECTILE_PRESETS
from ds1rand.features.spells import PRESETS as SPELL_PRESETS
from ds1rand.features.weapons import PRESETS as WEAPON_PRESETS

VERSION = 1
SHARE_PREFIX = "DS1R"


@dataclass
class RingsSettings:
    enabled: bool = True
    tier_weights: tuple[float, float, float, float] = RING_PRESETS["Standard"]
    isolate_npcs: bool = True
    write_summaries: bool = True


@dataclass
class SpellsSettings:
    enabled: bool = True
    tier_weights: tuple[float, float, float, float] = SPELL_PRESETS["Standard"]
    player: bool = True
    enemy: bool = True
    visual_chance: float = 0.6
    cross_school_visuals: bool = True
    status_chance: float = 0.15
    write_summaries: bool = True
    motion_chance: float = 0.4
    chain_chance: float = 0.35


@dataclass
class ProjectilesSettings:
    enabled: bool = True
    player_weights: tuple[float, float, float, float] = PROJECTILE_PRESETS["Standard"]
    enemy_weights: tuple[float, float, float, float] = ENEMY_PROJECTILE_PRESETS["Standard"]
    environment_weights: tuple[float, float, float, float] = ENEMY_PROJECTILE_PRESETS["Standard"]
    player: bool = True
    enemy: bool = True
    environment: bool = True
    visual_chance: float = 0.5
    motion_chance: float = 0.4
    chain_chance: float = 0.25
    status_chance: float = 0.15
    cross_enemy: bool = True
    spell_effects: bool = False
    write_summaries: bool = True
    enemy_spells: bool = True


@dataclass
class EnemiesSettings:
    enabled: bool = True
    tier_weights: tuple[float, float, float, float] = ENEMY_PRESETS["Standard"]
    turn: bool = True
    detection: bool = True
    pursuit: bool = True
    speed: bool = True
    poise: bool = True
    stamina: bool = True
    regular: bool = True
    bosses: bool = False
    humans: bool = False


@dataclass
class WeaponsSettings:
    enabled: bool = True
    tier_weights: tuple[float, float, float, float] = WEAPON_PRESETS["Standard"]
    weapons: bool = True
    shields: bool = True
    moveset_chance: float = 0.5
    effect_chance: float = 0.25
    element_chance: float = 0.15
    isolate_npcs: bool = True
    write_descriptions: bool = True


@dataclass
class ArmorSettings:
    enabled: bool = True
    tier_weights: tuple[float, float, float, float] = ARMOR_PRESETS["Standard"]
    set_tiers: bool = True
    effect_chance: float = 0.25
    isolate_npcs: bool = True
    write_descriptions: bool = True


@dataclass
class Preset:
    name: str = "Standard"
    seed: int | None = None  # None: pick one at random when running
    rings: RingsSettings = field(default_factory=RingsSettings)
    spells: SpellsSettings = field(default_factory=SpellsSettings)
    projectiles: ProjectilesSettings = field(default_factory=ProjectilesSettings)
    enemies: EnemiesSettings = field(default_factory=EnemiesSettings)
    weapons: WeaponsSettings = field(default_factory=WeaponsSettings)
    armor: ArmorSettings = field(default_factory=ArmorSettings)

    def to_dict(self) -> dict:
        return {"version": VERSION, **asdict(self)}

    @classmethod
    def from_dict(cls, data: dict) -> Preset:
        if data.get("version", VERSION) > VERSION:
            raise ValueError(f"Preset version {data['version']} is newer than this ds1rand (version {VERSION})")
        sections = {}
        for key, settings_cls in (("rings", RingsSettings), ("spells", SpellsSettings),
                                  ("projectiles", ProjectilesSettings), ("enemies", EnemiesSettings),
                                  ("weapons", WeaponsSettings), ("armor", ArmorSettings)):
            values = _known(settings_cls, data.get(key, {}))
            for name in ("tier_weights", "player_weights", "enemy_weights", "environment_weights"):
                if name in values:
                    values[name] = tuple(values[name])
            sections[key] = settings_cls(**values)
        return cls(name=data.get("name", "Custom"), seed=data.get("seed"), **sections)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, text: str) -> Preset:
        return cls.from_dict(json.loads(text))

    def save(self, path: Path | str) -> None:
        Path(path).write_text(self.to_json() + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path | str) -> Preset:
        return cls.from_json(Path(path).read_text(encoding="utf-8"))

    def to_share_string(self) -> str:
        packed = zlib.compress(json.dumps(self.to_dict(), separators=(",", ":")).encode("utf-8"), 9)
        return f"{SHARE_PREFIX}{VERSION}-{base64.urlsafe_b64encode(packed).decode('ascii').rstrip('=')}"

    @classmethod
    def from_share_string(cls, text: str) -> Preset:
        text = text.strip()
        prefix, _, body = text.partition("-")
        if not prefix.startswith(SHARE_PREFIX) or not body:
            raise ValueError("Not a ds1rand share string")
        packed = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        return cls.from_dict(json.loads(zlib.decompress(packed)))


def _known(cls, data: dict) -> dict:
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in names}


# Built-in global presets. Each sets every feature's section; features added later get their own defaults here.
BUILTIN: dict[str, Preset] = {
    name: Preset(name=name, rings=RingsSettings(tier_weights=RING_PRESETS[name]),
                 spells=SpellsSettings(tier_weights=SPELL_PRESETS[name]),
                 projectiles=ProjectilesSettings(player_weights=PROJECTILE_PRESETS[name],
                                                 enemy_weights=ENEMY_PROJECTILE_PRESETS[name],
                                                 environment_weights=ENEMY_PROJECTILE_PRESETS[name]),
                 enemies=EnemiesSettings(tier_weights=ENEMY_PRESETS[name]),
                 weapons=WeaponsSettings(tier_weights=WEAPON_PRESETS[name]),
                 armor=ArmorSettings(tier_weights=ARMOR_PRESETS[name]))
    for name in RING_PRESETS
}
