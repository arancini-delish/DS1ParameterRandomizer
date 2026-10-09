"""Ring randomizer (Phase 6.1), ported from the prototype (`legacy/ring_randomizer.py`).

Each ring gets a tier from the configured distribution, the tier picks a template of effect levels (e.g. one High
effect, or High + Medium + a Negative), and each level draws an effect from its pool. The ring's SpEffect is reset to
the plain ring template (the most common value of every field across the base's ring SpEffects; identical to the
prototype's `RingSpEffectParam.csv`) and the drawn effects are applied on top. The ring's summary text lists the
effects.

Rings keep their IDs (the player owns them by ID). Their SpEffects are copied when shared: with `isolate_npcs`, NPC
phantoms wearing a ring (CharaInitParam) get their own accessory and SpEffect copies and keep vanilla effects.
Pinned rings are left alone: by default the prototype's list (rings needed to progress or kept as they are).
"""
from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

from ds1rand.graph.model import Node
from ds1rand.session import Session


class Tier(IntEnum):
    STANDARD = 0
    UNCOMMON = 1
    RARE = 2
    LEGENDARY = 3


class Level(StrEnum):
    NEGATIVE = "Negative"
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    LEGENDARY = "Legendary"


@dataclass(frozen=True)
class RingEffect:
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
    return RingEffect(tuple(fields), tuple(values), picks, tuple(hidden))


_DAMAGE_CUTS = ("slashDamageCutRate", "blowDamageCutRate", "thrustDamageCutRate", "neutralDamageCutRate",
                "magicDamageCutRate", "fireDamageCutRate", "thunderDamageCutRate")
_DEFENSES = ("physicsDiffence", "magicDiffence", "fireDiffence", "thunderDiffence")
_ATTACK_RATES = ("physicsAttackPowerRate", "magicAttackPowerRate", "fireAttackPowerRate", "thunderAttackPowerRate")
_RESISTANCES = ("registPoizonChangeRate", "registCurseChangeRate", "registIllnessChangeRate", "registBloodChangeRate")
_MAX_HP = (("bCurrHPIndependeMaxHP", 1),)
_HP_REGEN = (("motionInterval", 1),)


def _state(state_info: int, hidden=()) -> RingEffect:
    return _e(("stateInfo",), (state_info,), hidden=hidden)


EFFECTS: dict[Level, list[RingEffect]] = {
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

# Tier -> ((weight, levels), ...)
TEMPLATES: dict[Tier, tuple[tuple[float, tuple[Level, ...]], ...]] = {
    Tier.STANDARD: ((0.8, (Level.LOW,)), (0.2, (Level.MEDIUM, Level.NEGATIVE))),
    Tier.UNCOMMON: ((0.6, (Level.MEDIUM,)), (0.2, (Level.LOW, Level.LOW)), (0.2, (Level.HIGH, Level.NEGATIVE))),
    Tier.RARE: ((0.6, (Level.HIGH,)), (0.2, (Level.MEDIUM, Level.LOW)),
                (0.2, (Level.HIGH, Level.MEDIUM, Level.NEGATIVE))),
    Tier.LEGENDARY: ((0.6, (Level.LEGENDARY,)), (0.2, (Level.HIGH, Level.MEDIUM)),
                     (0.2, (Level.LEGENDARY, Level.MEDIUM, Level.NEGATIVE))),
}

# Tier weights (Standard, Uncommon, Rare, Legendary), from the prototype UI.
PRESETS = {
    "Easy": (0.65, 0.2, 0.1, 0.05),
    "Standard": (0.7, 0.2, 0.08, 0.02),
    "Hard": (0.85, 0.1, 0.04, 0.01),
    "Misery": (0.9, 0.075, 0.02, 0.005),
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

# Prototype pins: Darkmoon Seance Ring, Covenant of Artorias, Orange Charred Ring (needed to progress), Ring of
# Sacrifice and Rare Ring of Sacrifice (kept as they are).
DEFAULT_PINNED = frozenset({149, 138, 139, 126, 127})


def summary(field: str, value) -> str:
    if field == "stateInfo":
        return STATE_SUMMARIES[value]
    spec = SUMMARIES[field]
    if isinstance(spec, tuple):
        spec, transform = spec
        value = transform(value)
    return spec.format(value=value)


@dataclass
class RingConfig:
    tier_weights: tuple[float, float, float, float] = PRESETS["Standard"]
    pinned: frozenset[int] = DEFAULT_PINNED
    write_summaries: bool = True
    isolate_npcs: bool = True
    max_effects: int = 4


@dataclass
class RingResult:
    ring_id: int
    speffect_id: int
    tier: Tier
    effects: dict[str, object] = field(default_factory=dict)
    summaries: list[str] = field(default_factory=list)


def ring_template(session: Session) -> dict[str, object]:
    """Most common value of every SpEffect field across the base's ring SpEffects: a ring with no effect."""
    rings = session.base.params["EquipParamAccessory"]
    speffects = session.base.params["SpEffectParam"]
    rows = [speffects.row_values(rings.row_values(r)["refId"]) for r in rings.rows if r]
    return {f: Counter(row[f] for row in rows).most_common(1)[0][0] for f in speffects.fields}


def _roll_ring(rng: random.Random, config: RingConfig) -> tuple[Tier, dict[str, object], list[str]]:
    tier = Tier(rng.choices(range(len(Tier)), weights=config.tier_weights)[0])
    templates = TEMPLATES[tier]
    levels = rng.choices([t[1] for t in templates], weights=[t[0] for t in templates])[0]
    values: dict[str, object] = {}
    summaries: list[str] = []
    for level in levels:
        candidates = [e for e in EFFECTS[level]
                      if not e.all_fields & set(values) and len(summaries) + e.count <= config.max_effects]
        if not candidates:
            continue
        effect = rng.choice(candidates)
        rolled = effect.roll(rng)
        values.update(rolled)
        values.update(dict(effect.hidden))
        summaries += [summary(f, v) for f, v in rolled.items()]
    return tier, values, summaries


def randomize_rings(session: Session, config: RingConfig, rng: random.Random) -> list[RingResult]:
    enabled = ["ring", "enemy"] if config.isolate_npcs else ["ring"]
    params = {"EquipParamAccessory", "SpEffectParam"}
    allocation = session.allocate(enabled, params=params, rows=session.footprint("ring", params))
    template = ring_template(session)
    rings = session.base.params["EquipParamAccessory"]
    results = []
    for ring_id in sorted(r for r in rings.rows if r and r not in config.pinned):
        original = rings.row_values(ring_id)["refId"]
        speffect = allocation.row_for(Node.param("SpEffectParam", original), "ring")
        tier, effects, summaries = _roll_ring(rng, config)
        session.store.set("SpEffectParam", speffect, {**template, **effects})
        if config.write_summaries:
            session.text[("Accessory_description", ring_id)] = ", ".join(summaries)
        results.append(RingResult(ring_id, speffect, tier, effects, summaries))
    return results
