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
from dataclasses import dataclass, field
from enum import IntEnum

from ds1rand.features.passives import (  # noqa: F401  (re-exported: the ring effect tables live there now)
    EFFECTS, STATE_SUMMARIES, SUMMARIES, Level, PassiveEffect, passive_template, roll_passive, summary,
)
from ds1rand.graph.model import Node
from ds1rand.session import Session

RingEffect = PassiveEffect
ring_template = passive_template


class Tier(IntEnum):
    STANDARD = 0
    UNCOMMON = 1
    RARE = 2
    LEGENDARY = 3


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

# Prototype pins: Darkmoon Seance Ring, Covenant of Artorias, Orange Charred Ring (needed to progress), Ring of
# Sacrifice and Rare Ring of Sacrifice (kept as they are).
DEFAULT_PINNED = frozenset({149, 138, 139, 126, 127})


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


def _roll_ring(rng: random.Random, config: RingConfig) -> tuple[Tier, dict[str, object], list[str]]:
    tier = Tier(rng.choices(range(len(Tier)), weights=config.tier_weights)[0])
    templates = TEMPLATES[tier]
    levels = rng.choices([t[1] for t in templates], weights=[t[0] for t in templates])[0]
    values, summaries = roll_passive(rng, levels, config.max_effects)
    return tier, values, summaries


def randomize_rings(session: Session, config: RingConfig, rng: random.Random) -> list[RingResult]:
    enabled = ["ring", "enemy"] if config.isolate_npcs else ["ring"]
    params = {"EquipParamAccessory", "SpEffectParam"}
    allocation = session.allocate(enabled, params=params, rows=session.footprint("ring", params))
    template = passive_template(session)
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
