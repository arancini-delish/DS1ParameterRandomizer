"""Presets: every setting of a run, versioned, as JSON files or a short share string.

A preset holds one section per feature (rings, spells; projectiles and enemy behaviour as they are built) plus the
seed. Share strings are "DS1R" + version + "-" + base64url(zlib(JSON)), so pasting one reproduces a run exactly.
Unknown keys are ignored and missing keys take defaults, so presets from older versions keep loading.
"""
from __future__ import annotations

import base64
import json
import zlib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from ds1rand.features.rings import PRESETS as RING_PRESETS
from ds1rand.features.spells import PRESETS as SPELL_PRESETS

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
    visual_chance: float = 0.5
    cross_school_visuals: bool = False
    status_chance: float = 0.15
    write_summaries: bool = True


@dataclass
class Preset:
    name: str = "Standard"
    seed: int | None = None  # None: pick one at random when running
    rings: RingsSettings = field(default_factory=RingsSettings)
    spells: SpellsSettings = field(default_factory=SpellsSettings)

    def to_dict(self) -> dict:
        return {"version": VERSION, **asdict(self)}

    @classmethod
    def from_dict(cls, data: dict) -> Preset:
        if data.get("version", VERSION) > VERSION:
            raise ValueError(f"Preset version {data['version']} is newer than this ds1rand (version {VERSION})")
        sections = {}
        for key, settings_cls in (("rings", RingsSettings), ("spells", SpellsSettings)):
            values = _known(settings_cls, data.get(key, {}))
            if "tier_weights" in values:
                values["tier_weights"] = tuple(values["tier_weights"])
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
                 spells=SpellsSettings(tier_weights=SPELL_PRESETS[name]))
    for name in RING_PRESETS
}
