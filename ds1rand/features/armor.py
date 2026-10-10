"""Armor randomizer (Phase 6.6): rarity tiers with a cost model, and passive effects with ring-style text.

Armor sets (pieces sharing `id // 10000`: helm, chest, gauntlets, leggings) draw one rarity tier by default
(`set_tiers`; off: each piece draws its own). As with weapons, the tier sets a target value relative to the vanilla
piece and the closest of many random candidates wins, so common armor trades strengths for weaknesses:

    value = DEFENSE x ln(defense ratio) + RESISTANCE x ln(resistance ratio) + POISE x ln(poise ratio)
            + WEIGHT x ln(weight ratio) + added effect
Defense counts physical (with its slash / strike / thrust offsets) and elemental defense; resistance the four status
resistances; poise is `saDurability` (pieces without poise may gain a little).

Effects (`effect_chance` per piece, level by tier, commons sometimes negative): a ring-style passive
(`features.passives`) in a free resident SpEffect slot; vanilla effects are kept (Crown of Dusk, Mask of the Father,
Symbol of Avarice..., and the shared plumbing SpEffects most armor carries). Rarity and effect go into the piece's
long description.

Pinned: unnamed (unused) rows and the bare body parts (no-armor rows: no weight, no defense). With `isolate_npcs`,
NPCs and invaders keep vanilla copies of the armor they wear.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import IntEnum

from ds1rand.catalogue.budget import reference_limits
from ds1rand.features.passives import Level, passive_template, roll_passive
from ds1rand.session import Session


class ArmorTier(IntEnum):
    COMMON = 0
    UNCOMMON = 1
    RARE = 2
    LEGENDARY = 3


TIER_VALUE = {ArmorTier.COMMON: 0.82, ArmorTier.UNCOMMON: 1.0, ArmorTier.RARE: 1.18, ArmorTier.LEGENDARY: 1.4}
TIER_LEVEL = {ArmorTier.COMMON: Level.LOW, ArmorTier.UNCOMMON: Level.MEDIUM, ArmorTier.RARE: Level.HIGH,
              ArmorTier.LEGENDARY: Level.LEGENDARY}
EFFECT_VALUE = {Level.NEGATIVE: -0.08, Level.LOW: 0.04, Level.MEDIUM: 0.08, Level.HIGH: 0.12, Level.LEGENDARY: 0.16}
PRESETS = {
    "Easy": (0.3, 0.35, 0.25, 0.1),
    "Standard": (0.4, 0.35, 0.2, 0.05),
    "Hard": (0.55, 0.3, 0.12, 0.03),
    "Misery": (0.7, 0.22, 0.07, 0.01),
}

PHYSICAL = "defensePhysics"
OFFSETS = ("defenseSlash", "defenseBlow", "defenseThrust")
ELEMENTAL = ("defenseMagic", "defenseFire", "defenseThunder")
RESISTANCES = ("resistPoison", "resistDisease", "resistBlood", "resistCurse")
RESIDENT = ("residentSpEffectId", "residentSpEffectId2", "residentSpEffectId3")
WEIGHTS = {"defense": 0.4, "resistance": 0.12, "poise": 0.18, "weight": 0.3}
CANDIDATES = 48
NEGATIVE_CHANCE = 0.3  # commons' effect is a negative one this often
STANDALONE_EXCLUDED = frozenset({"conditionHp"})


@dataclass
class ArmorConfig:
    tier_weights: tuple[float, float, float, float] = PRESETS["Standard"]
    set_tiers: bool = True
    effect_chance: float = 0.25
    isolate_npcs: bool = True
    write_descriptions: bool = True


@dataclass
class ArmorResult:
    armor_id: int
    tier: ArmorTier
    value: float = 0.0
    changes: dict[str, object] = field(default_factory=dict)
    effects: list[str] = field(default_factory=list)


def defense(values: dict) -> float:
    physical = values[PHYSICAL] + sum(values[f] for f in OFFSETS) / 3 * 0.5
    return max(0.0, physical) + 0.7 * sum(values[f] for f in ELEMENTAL) / 3


def value(new: dict, old: dict, effect: float = 0.0) -> float:
    ratios = {
        "defense": (defense(new) + 5) / (defense(old) + 5),
        "resistance": (sum(new[f] for f in RESISTANCES) + 10) / (sum(old[f] for f in RESISTANCES) + 10),
        "poise": (new["saDurability"] + 5) / (old["saDurability"] + 5),
        "weight": (old["weight"] + 1) / (new["weight"] + 1),
    }
    return sum(WEIGHTS[k] * math.log(r) for k, r in ratios.items()) + effect


def is_pinned(armor_id: int, values: dict, names: dict[int, str]) -> bool:
    bare = not values["weight"] and not values[PHYSICAL] and not any(values[f] for f in ELEMENTAL)
    return not armor_id or not names.get(armor_id) or bare


def _log_uniform(rng: random.Random, low: float, high: float) -> float:
    return math.exp(rng.uniform(math.log(low), math.log(high)))


class _ArmorBuilder:
    def __init__(self, session: Session, config: ArmorConfig, rng: random.Random):
        self.session = session
        self.config = config
        self.rng = rng
        self.armor = session.base.params["EquipParamProtector"]
        self.template = passive_template(session)
        rings = session.base.params["EquipParamAccessory"]
        self.template_row = rings.row_values(min(r for r in rings.rows if r))["refId"]
        limits = reference_limits(session.base)["SpEffectParam"]
        self.speffect_max = {f: limits.get(("EquipParamProtector", f), 2**31 - 1) for f in RESIDENT}

    def tier(self) -> ArmorTier:
        return ArmorTier(self.rng.choices(range(len(ArmorTier)), weights=self.config.tier_weights)[0])

    def candidate(self, old: dict) -> dict:
        rng = self.rng
        new = dict(old)
        overall = _log_uniform(rng, 0.6, 1.6)
        for name in (PHYSICAL, *OFFSETS, *ELEMENTAL):
            new[name] = round(old[name] * overall * _log_uniform(rng, 0.85, 1.18))
        for name in RESISTANCES:
            new[name] = round(old[name] * _log_uniform(rng, 0.5, 1.8))
        if old["saDurability"] > 0:
            new["saDurability"] = round(old["saDurability"] * _log_uniform(rng, 0.5, 1.8))
        elif rng.random() < 0.3:
            new["saDurability"] = rng.randint(1, 8)
        if old["weight"]:
            new["weight"] = max(0.1, round(old["weight"] * _log_uniform(rng, 0.7, 1.4), 1))
        return new

    def effect(self, tier: ArmorTier) -> tuple[tuple[dict, list[str]] | None, float]:
        rng = self.rng
        if rng.random() >= self.config.effect_chance:
            return None, 0.0
        level = Level.NEGATIVE if tier == ArmorTier.COMMON and rng.random() < NEGATIVE_CHANCE else TIER_LEVEL[tier]
        values, summaries = roll_passive(rng, (level,), max_effects=2, exclude=STANDALONE_EXCLUDED)
        return ((values, summaries), EFFECT_VALUE[level]) if summaries else (None, 0.0)

    def build(self, armor_id: int, tier: ArmorTier) -> ArmorResult:
        old = self.armor.row_values(armor_id)
        effect, effect_value = self.effect(tier)
        slot = next((s for s in RESIDENT if old[s] <= 0), None)
        if slot is None:
            effect, effect_value = None, 0.0
        target = math.log(TIER_VALUE[tier])
        best = min((self.candidate(old) for _ in range(CANDIDATES)),
                   key=lambda new: abs(value(new, old, effect_value) - target))
        result = ArmorResult(armor_id, tier)
        if effect is not None:
            values, summaries = effect
            speffect = self.session.ids.allocate("SpEffectParam", self.speffect_max[slot])
            self.session.store.add("SpEffectParam", speffect, copy_from=self.template_row)
            self.session.store.set("SpEffectParam", speffect, {**self.template, **values})
            best[slot] = speffect
            result.effects = ["While worn: " + ", ".join(summaries)]
        result.value = math.exp(value(best, old, effect_value))
        result.changes = {f: best[f] for f in best if best[f] != old[f]}
        self.session.store.set("EquipParamProtector", armor_id, result.changes)
        return result


def describe(result: ArmorResult, long_desc: str | None) -> str | None:
    """The piece's long description headed by its rarity and effect."""
    if long_desc is None:
        return None
    head = "\n".join([f"Rarity: {result.tier.name.title()}", *result.effects])
    return head + "\n" + long_desc if long_desc.startswith("\n") else head + "\n\n" + long_desc


def randomize_armor(session: Session, config: ArmorConfig, rng: random.Random) -> list[ArmorResult]:
    armor = session.base.params["EquipParamProtector"]
    if config.isolate_npcs:
        params = {"EquipParamProtector"}
        session.allocate(["player_armor", "enemy"], params=params, rows=session.footprint("player_armor", params))
    builder = _ArmorBuilder(session, config, rng)
    names = session.base.text.get(12, ("", {}))[1]
    long_descs = session.base.text.get(26, ("", {}))[1]
    set_tiers: dict[int, ArmorTier] = {}
    results = []
    for armor_id in sorted(armor.rows):
        if is_pinned(armor_id, armor.row_values(armor_id), names):
            continue
        if config.set_tiers:
            tier = set_tiers.setdefault(armor_id // 10000, builder.tier())
        else:
            tier = builder.tier()
        result = builder.build(armor_id, tier)
        if config.write_descriptions:
            text = describe(result, long_descs.get(armor_id) or None)
            if text:
                session.text[("Armor_long_desc", armor_id)] = text
        results.append(result)
    return results
