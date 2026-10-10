"""Passive effects worn or held by the player, shared by rings, weapons (while held) and armor (6.1, 6.5, 6.6).

A passive is a SpEffect built from the plain ring template (`passive_template`: the most common value of every field
across the ring SpEffects, i.e. an effect that does nothing while worn) with effects drawn per level from `EFFECTS`
on top. `summary` gives each effect's in-game text, e.g. "Max HP: 110%".
"""
from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from ds1rand.session import Session


class Level(StrEnum):
    NEGATIVE = "Negative"
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    LEGENDARY = "Legendary"


@dataclass(frozen=True)
class PassiveEffect:
    """Sets `picks` of `fields` (all if None) to their `values`; `hidden` fields are always set and not described."""
    fields: tuple[str, ...]
    values: tuple
    picks: int | None = None
    hidden: tuple[tuple[str, object], ...] = ()

    @property
    def count(self) -> int:
        return self.picks or len(self.fields)

    @property
    def all_fields(self) -> set[str]:
        return set(self.fields) | {f for f, _ in self.hidden}

    def roll(self, rng: random.Random) -> dict[str, object]:
        chosen = rng.sample(list(zip(self.fields, self.values)), self.count)
        return dict(chosen)


def _e(fields, values, picks=None, hidden=()):
    return PassiveEffect(tuple(fields), tuple(values), picks, tuple(hidden))


_DAMAGE_CUTS = ("slashDamageCutRate", "blowDamageCutRate", "thrustDamageCutRate", "neutralDamageCutRate",
                "magicDamageCutRate", "fireDamageCutRate", "thunderDamageCutRate")
_DEFENSES = ("physicsDiffence", "magicDiffence", "fireDiffence", "thunderDiffence")
_ATTACK_RATES = ("physicsAttackPowerRate", "magicAttackPowerRate", "fireAttackPowerRate", "thunderAttackPowerRate")
_RESISTANCES = ("registPoizonChangeRate", "registCurseChangeRate", "registIllnessChangeRate", "registBloodChangeRate")
_MAX_HP = (("bCurrHPIndependeMaxHP", 1),)
_HP_REGEN = (("motionInterval", 1),)


def _state(state_info: int, hidden=()) -> PassiveEffect:
    return _e(("stateInfo",), (state_info,), hidden=hidden)


EFFECTS: dict[Level, list[PassiveEffect]] = {
    Level.NEGATIVE: [
        _e(["physicsDiffence"], [-25]),
        _e(_DEFENSES, [-20] * 4, 2),
        _e(_DAMAGE_CUTS, [1.15] * 7, 2),
        _e(_ATTACK_RATES, [0.8] * 4, 1),
        _e(["equipWeightChangeRate"], [0.8]),
        _e(["conditionHp"], [0.5]),
        _e(["staminaRecoverChangeSpeed"], [-10]),
        _e(_RESISTANCES, [0.5] * 4, 2),
        _e(["maxHpRate"], [0.75], hidden=_MAX_HP),
        _e(["changeHpRate"], [1], hidden=_HP_REGEN),
        _e(["maxStaminaRate"], [0.75]),
        _e(["bowDistRate"], [-20]),
        _e(["changeSuperArmorPoint"], [-20]),
        _e(["soulRate"], [0.8]),
    ],
    Level.LOW: [
        _e(["physicsDiffence"], [15]),
        _e(_DEFENSES, [10] * 4, 2),
        _e(_DAMAGE_CUTS, [0.9] * 7, 2),
        _e(_ATTACK_RATES, [1.1] * 4, 1),
        _e(["equipWeightChangeRate"], [1.1]),
        _e(["changeMagicSlot"], [1]),
        _e(["sightSearchEnemyCut"], [35]),
        _e(["maxDurability"], [10]),
        _e(["staminaRecoverChangeSpeed"], [5]),
        _e(_RESISTANCES, [1.25] * 4, 2),
        _e(["maxHpRate"], [1.05], hidden=_MAX_HP),
        _e(["changeHpRate"], [-0.5], hidden=_HP_REGEN),
        _e(["maxStaminaRate"], [1.1]),
        _e(["bowDistRate"], [10]),
        _e(["changeSuperArmorPoint"], [10]),
        _e(["soulRate"], [1.05]),
    ],
    Level.MEDIUM: [
        _e(["hearingSearchEnemyCut"], [100]),
        _e(["sightSearchEnemyCut"], [70]),
        _state(66),  # item discovery
        _state(115),  # better dodge
        _state(199, hidden=(("effectTargetFriend", 0), ("effectTargetEnemy", 0), ("magParamChange", 1),
                            ("miracleParamChange", 1))),  # absorb HP on hit
        _e(["physicsDiffence"], [25]),
        _e(_DEFENSES, [20] * 4, 2),
        _e(_DAMAGE_CUTS, [0.8] * 7, 2),
        _e(_ATTACK_RATES, [1.15] * 4, 1),
        _e(["equipWeightChangeRate"], [1.2]),
        _e(["staminaRecoverChangeSpeed"], [10]),
        _e(_RESISTANCES, [1.5] * 4, 2),
        _e(["maxHpRate"], [1.1], hidden=_MAX_HP),
        _e(["changeHpRate"], [-1], hidden=_HP_REGEN),
        _e(["maxStaminaRate"], [1.2]),
        _e(["bowDistRate"], [30]),
        _e(["changeSuperArmorPoint"], [20]),
        _e(["soulRate"], [1.1]),
    ],
    Level.HIGH: [
        _e(["physicsDiffence"], [50]),
        _e(_DEFENSES, [35] * 4, 2),
        _e(_DAMAGE_CUTS, [0.75] * 7, 2),
        _e(_ATTACK_RATES, [1.2] * 4, 1),
        _e(["equipWeightChangeRate"], [1.35]),
        _e(["staminaRecoverChangeSpeed"], [20]),
        _e(_RESISTANCES, [1.5] * 4, 2),
        _e(["maxHpRate"], [1.2], hidden=_MAX_HP),
        _e(["maxStaminaRate"], [1.35]),
        _e(["changeSuperArmorPoint"], [40]),
        _e(["soulRate"], [1.25]),
    ],
    Level.LEGENDARY: [
        _e(["physicsDiffence"], [75]),
        _e(_DEFENSES, [40] * 4, 2),
        _e(_DAMAGE_CUTS, [0.7] * 7, 2),
        _e(_ATTACK_RATES, [1.25] * 4, 1),
        _e(["equipWeightChangeRate"], [1.5]),
        _e(["staminaRecoverChangeSpeed"], [30]),
        _e(_RESISTANCES, [4] * 4, 2),
        _e(["maxHpRate"], [1.3], hidden=_MAX_HP),
        _e(["maxStaminaRate"], [1.45]),
        _e(["changeSuperArmorPoint"], [60]),
        _e(["soulRate"], [1.5]),
    ],
}


# Summary text per field: format string, or (format string, value transform).
SUMMARIES: dict[str, str | tuple[str, object]] = {
    "physicsDiffence": "Physical Defense: {value:+g}",
    "magicDiffence": "Magic Defense: {value:+g}",
    "fireDiffence": "Fire Defense: {value:+g}",
    "thunderDiffence": "Lightning Defense: {value:+g}",
    "equipWeightChangeRate": "Equipment Weight Capacity: {value:.0%}",
    "staminaRecoverChangeSpeed": "Stamina Recovery Speed: {value:+g}",
    "conditionHp": "Ring effects activate at {value:.0%} HP",
    "physicsAttackPowerRate": "Physical Attack Power: {value:.0%}",
    "magicAttackPowerRate": "Magic Attack Power: {value:.0%}",
    "fireAttackPowerRate": "Fire Attack Power: {value:.0%}",
    "thunderAttackPowerRate": "Lightning Attack Power: {value:.0%}",
    "registPoizonChangeRate": "Poison Resistance: {value:.0%}",
    "registCurseChangeRate": "Curse Resistance: {value:.0%}",
    "registIllnessChangeRate": "Disease Resistance: {value:.0%}",
    "registBloodChangeRate": "Blood Loss Resistance: {value:.0%}",
    "changeMagicSlot": "Attunement Slots: {value:+g}",
    "maxHpRate": "Max HP: {value:.0%}",
    "changeHpRate": ("HP % per Sec: {value:+g}%", lambda v: -v),
    "bowDistRate": "Arrow Distance: {value:+g}%",
    "changeSuperArmorPoint": "Poise: {value:+g}",
    "soulRate": "Additional Souls: {value:.0%}",
    "sightSearchEnemyCut": ("Enemy Sight Range: {value:+g}%", lambda v: -v),  # a reduction
    "hearingSearchEnemyCut": ("Enemy Hearing Range: {value:+g}%", lambda v: -v),
    "maxStaminaRate": "Max Stamina: {value:.0%}",
    "maxDurability": "Equipment Durability: {value:+g}",
    "slashDamageCutRate": "Slash Damage Taken: {value:.0%}",
    "blowDamageCutRate": "Strike Damage Taken: {value:.0%}",
    "thrustDamageCutRate": "Thrust Damage Taken: {value:.0%}",
    "neutralDamageCutRate": "Physical Damage Taken: {value:.0%}",
    "magicDamageCutRate": "Magic Damage Taken: {value:.0%}",
    "fireDamageCutRate": "Fire Damage Taken: {value:.0%}",
    "thunderDamageCutRate": "Lightning Damage Taken: {value:.0%}",
}
STATE_SUMMARIES = {66: "Item Discovery +", 115: "Better Dodge", 193: "Spell Duration +", 199: "Absorb HP on hit"}


def summary(field: str, value) -> str:
    if field == "stateInfo":
        return STATE_SUMMARIES[value]
    spec = SUMMARIES[field]
    if isinstance(spec, tuple):
        spec, transform = spec
        value = transform(value)
    return spec.format(value=value)


def passive_template(session: Session) -> dict[str, object]:
    """Most common value of every SpEffect field across the base's ring SpEffects: a ring with no effect."""
    rings = session.base.params["EquipParamAccessory"]
    speffects = session.base.params["SpEffectParam"]
    rows = [speffects.row_values(rings.row_values(r)["refId"]) for r in rings.rows if r]
    return {f: Counter(row[f] for row in rows).most_common(1)[0][0] for f in speffects.fields}


def roll_passive(rng: random.Random, levels, max_effects: int = 4, taken: dict | None = None,
                 exclude: frozenset[str] = frozenset()) -> tuple[dict[str, object], list[str]]:
    """Draw one effect per level (skipping effects whose fields are already set or in `exclude`); returns SpEffect
    values and their summaries."""
    values: dict[str, object] = dict(taken or {})
    summaries: list[str] = []
    for level in levels:
        candidates = [e for e in EFFECTS[level]
                      if not e.all_fields & (set(values) | exclude) and len(summaries) + e.count <= max_effects]
        if not candidates:
            continue
        effect = rng.choice(candidates)
        rolled = effect.roll(rng)
        values.update(rolled)
        values.update(dict(effect.hidden))
        summaries += [summary(f, v) for f, v in rolled.items()]
    for name in taken or {}:
        values.pop(name, None)
    return values, summaries
