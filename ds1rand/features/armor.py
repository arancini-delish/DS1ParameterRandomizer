"""Armor randomizer (Phase 6.6): armor generated from scratch by rarity, with passive effects and ring-style text.

Pieces are not scaled from their vanilla stats: each one is generated anew for its slot (helm, chest, gauntlets,
leggings), so a huge suit may come out light with good magic defense, or a light hat with enormous poise and no slash
defense. Every stat is drawn as a percentile of that slot's vanilla values (weight inverted: a high percentile is a
light piece) and mapped back through the vanilla distribution, so values always look like real armor of that slot.

A piece's rating is the weighted mean percentile of its stats (`RATING_WEIGHTS`) plus its effect (`EFFECT_RATING`).
The rarity tier picks where the rating falls within the distribution of vanilla ratings for the slot (`TIER_BAND`:
commons in the lower part, legendaries at the top), so across all armor the ratings follow vanilla's. Many candidates
are generated, from spiky draws that favour extremes, and the one closest to the target rating wins.

Armor sets (pieces sharing `id // 10000`) draw one tier by default (`set_tiers`; off: each piece draws its own).
Effects (`effect_chance` per piece, level by tier, commons sometimes negative): a ring-style passive
(`features.passives`) in a free resident SpEffect slot; vanilla effects are kept (Crown of Dusk, Mask of the Father,
Symbol of Avarice..., and the shared plumbing SpEffects most armor carries). Rarity and effect head the piece's long
description.

Pinned: unnamed (unused) rows and the bare body parts (no weight, no defense). With `isolate_npcs`, NPCs and invaders
keep vanilla copies of the armor they wear.
"""
from __future__ import annotations

import bisect
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


# Where a tier's rating falls in the vanilla rating distribution of the slot (percentile range).
TIER_BAND = {ArmorTier.COMMON: (0.0, 0.45), ArmorTier.UNCOMMON: (0.3, 0.7), ArmorTier.RARE: (0.6, 0.9),
             ArmorTier.LEGENDARY: (0.88, 1.0)}
TIER_LEVEL = {ArmorTier.COMMON: Level.LOW, ArmorTier.UNCOMMON: Level.MEDIUM, ArmorTier.RARE: Level.HIGH,
              ArmorTier.LEGENDARY: Level.LEGENDARY}
EFFECT_RATING = {Level.NEGATIVE: -0.03, Level.LOW: 0.02, Level.MEDIUM: 0.04, Level.HIGH: 0.06, Level.LEGENDARY: 0.08}
PRESETS = {
    "Easy": (0.3, 0.35, 0.25, 0.1),
    "Standard": (0.4, 0.35, 0.2, 0.05),
    "Hard": (0.55, 0.3, 0.12, 0.03),
    "Misery": (0.7, 0.22, 0.07, 0.01),
}

SLOTS = ("headEquip", "bodyEquip", "armEquip", "legEquip")
RATING_WEIGHTS = {
    "weight": 0.24,  # inverted: lighter is better
    "saDurability": 0.16,
    "defensePhysics": 0.2,
    "defenseSlash": 0.03, "defenseBlow": 0.03, "defenseThrust": 0.03,
    "defenseMagic": 0.06, "defenseFire": 0.06, "defenseThunder": 0.06,
    "resistPoison": 0.03, "resistDisease": 0.03, "resistBlood": 0.03, "resistCurse": 0.03,
}
INVERTED = frozenset({"weight"})
ELEMENTAL = ("defenseMagic", "defenseFire", "defenseThunder")
RESIDENT = ("residentSpEffectId", "residentSpEffectId2", "residentSpEffectId3")
CANDIDATES = 200
SPIKE = 1.5  # lower: stats of a candidate spread further from its centre (more extremes)
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
    value: float = 0.0  # rating as a percentile of the slot's vanilla ratings (0-1)
    changes: dict[str, object] = field(default_factory=dict)
    effects: list[str] = field(default_factory=list)


def is_pinned(armor_id: int, values: dict, names: dict[int, str]) -> bool:
    bare = not values["weight"] and not values["defensePhysics"] and not any(values[f] for f in ELEMENTAL)
    return not armor_id or not names.get(armor_id) or bare


def slot_of(values: dict) -> str:
    return next((s for s in SLOTS if values[s]), "bodyEquip")


class SlotModel:
    """Vanilla value distributions of one armor slot: stat <-> percentile, and the distribution of ratings."""

    def __init__(self, rows: list[dict]):
        self.values = {f: sorted(row[f] for row in rows) for f in RATING_WEIGHTS}
        self.ratings = sorted(self.rating(row) for row in rows)

    def percentile(self, name: str, value) -> float:
        """Mid-rank percentile of `value` among the slot's vanilla values (inverted for weight)."""
        values = self.values[name]
        low, high = bisect.bisect_left(values, value), bisect.bisect_right(values, value)
        q = (low + high) / 2 / len(values)
        return 1 - q if name in INVERTED else q

    def value_at(self, name: str, q: float):
        """The vanilla value at percentile `q` (inverted for weight), interpolated."""
        values = self.values[name]
        q = 1 - q if name in INVERTED else q
        position = q * (len(values) - 1)
        low = int(position)
        high = min(low + 1, len(values) - 1)
        value = values[low] + (values[high] - values[low]) * (position - low)
        return round(value, 1) if isinstance(values[0], float) else int(round(value))

    def rating(self, row: dict, effect: float = 0.0) -> float:
        return sum(w * self.percentile(f, row[f]) for f, w in RATING_WEIGHTS.items()) + effect

    def rating_at(self, q: float) -> float:
        position = min(max(q, 0.0), 1.0) * (len(self.ratings) - 1)
        low = int(position)
        high = min(low + 1, len(self.ratings) - 1)
        return self.ratings[low] + (self.ratings[high] - self.ratings[low]) * (position - low)

    def rating_percentile(self, rating: float) -> float:
        return bisect.bisect_left(self.ratings, rating) / len(self.ratings)


class _ArmorBuilder:
    def __init__(self, session: Session, config: ArmorConfig, rng: random.Random):
        self.session = session
        self.config = config
        self.rng = rng
        self.armor = session.base.params["EquipParamProtector"]
        names = session.base.text.get(12, ("", {}))[1]
        rows = [self.armor.row_values(a) for a in self.armor.rows
                if not is_pinned(a, self.armor.row_values(a), names)]
        self.models = {slot: SlotModel([r for r in rows if slot_of(r) == slot]) for slot in SLOTS}
        self.template = passive_template(session)
        rings = session.base.params["EquipParamAccessory"]
        self.template_row = rings.row_values(min(r for r in rings.rows if r))["refId"]
        limits = reference_limits(session.base)["SpEffectParam"]
        self.speffect_max = {f: limits.get(("EquipParamProtector", f), 2**31 - 1) for f in RESIDENT}

    def tier(self) -> ArmorTier:
        return ArmorTier(self.rng.choices(range(len(ArmorTier)), weights=self.config.tier_weights)[0])

    def candidate(self, model: SlotModel) -> dict[str, float]:
        """Stat percentiles scattered around a random centre (spiky: extremes are common)."""
        rng = self.rng
        centre = rng.uniform(0.02, 0.98)
        return {f: rng.betavariate(SPIKE * centre + 0.1, SPIKE * (1 - centre) + 0.1) for f in RATING_WEIGHTS}

    def effect(self, tier: ArmorTier) -> tuple[tuple[dict, list[str]] | None, float]:
        rng = self.rng
        if rng.random() >= self.config.effect_chance:
            return None, 0.0
        level = Level.NEGATIVE if tier == ArmorTier.COMMON and rng.random() < NEGATIVE_CHANCE else TIER_LEVEL[tier]
        values, summaries = roll_passive(rng, (level,), max_effects=2, exclude=STANDALONE_EXCLUDED)
        return ((values, summaries), EFFECT_RATING[level]) if summaries else (None, 0.0)

    def build(self, armor_id: int, tier: ArmorTier) -> ArmorResult:
        old = self.armor.row_values(armor_id)
        model = self.models[slot_of(old)]
        effect, effect_rating = self.effect(tier)
        slot = next((s for s in RESIDENT if old[s] <= 0), None)
        if slot is None:
            effect, effect_rating = None, 0.0
        target = model.rating_at(self.rng.uniform(*TIER_BAND[tier]))
        best = min(
            (self.candidate(model) for _ in range(CANDIDATES)),
            key=lambda q: abs(sum(RATING_WEIGHTS[f] * q[f] for f in q) + effect_rating - target),
        )
        new = dict(old)
        new.update({f: model.value_at(f, q) for f, q in best.items()})
        result = ArmorResult(armor_id, tier)
        if effect is not None:
            values, summaries = effect
            speffect = self.session.ids.allocate("SpEffectParam", self.speffect_max[slot])
            self.session.store.add("SpEffectParam", speffect, copy_from=self.template_row)
            self.session.store.set("SpEffectParam", speffect, {**self.template, **values})
            new[slot] = speffect
            result.effects = ["While worn: " + ", ".join(summaries)]
        result.value = model.rating_percentile(model.rating(new, effect_rating))
        result.changes = {f: new[f] for f in new if new[f] != old[f]}
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
