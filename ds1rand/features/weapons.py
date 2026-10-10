"""Weapon randomizer (Phase 6.5): rarity tiers with a cost model, scaling that matches damage, effects, movesets.

Every weapon row is randomized on its own, infusion paths included (Crystal, Divine... rows are weapons of their own;
their upgrade growth still comes from the shared reinforce tables). Each row draws a rarity tier; the tier sets a
target value relative to the vanilla weapon (`TIER_VALUE`). Many random candidates are generated and the one whose
value is closest to the target wins, so common weapons trade strengths for weaknesses and rare ones come out ahead:

    value = OFFENSE x ln(attack rating ratio) + WEIGHT x ln(weight ratio) + REQUIREMENTS x ln(requirement ratio)
            + GUARD x ln(guard ratio) + added effects
The attack rating is taken at reference stats (`REFERENCE_SCALING`): scaling only counts for the damage it scales,
so heavy faith scaling on a weapon with little magic damage is worth little. Scaling rules follow the engine: strength
/ dexterity scale physical damage, intelligence / faith scale magic damage, fire and lightning do not scale; scaling
is only given to stats that scale a damage type the weapon deals above a negligible share (`NEGLIGIBLE`). Some weapons
move part of their physical damage into an element (`element_chance`), which can open intelligence / faith scaling.
Stats a weapon scales well with get a matching requirement. The in-game scaling letters are computed from these values.

Shields value guarding most (`SHIELD_WEIGHTS`): physical / elemental guard, stability and status resistance.

Effects (`effect_chance` each, level by tier): on hit, a status buildup (bleed / poison / toxic) or HP restored per
hit (not shields); while held, a ring-style passive (`features.passives`). They go into free slots; vanilla effects are kept (e.g.
the Chaos Blade's self-damage). The effects, the rarity and a moveset change are written into the weapon's
description.

Movesets (`moveset_chance`, per weapon family = a base weapon and its infusion rows): a weapon may take the moveset of
another weapon of its type and animation set (attacks, motion values and stamina costs come with the moveset).

Pinned: fists, catalysts / talismans / pyromancy flames, ammo, lanterns, the Dark Hand. Starting classes can always use their starting
weapons and shields (requirements are capped at the class's stats). With `isolate_npcs`, NPCs and invaders keep
vanilla copies of the weapons they carry.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from enum import IntEnum

from ds1rand.catalogue.budget import reference_limits
from ds1rand.features.passives import Level, passive_template, roll_passive
from ds1rand.graph.model import Node
from ds1rand.session import Session


class WeaponTier(IntEnum):
    COMMON = 0
    UNCOMMON = 1
    RARE = 2
    LEGENDARY = 3


TIER_VALUE = {WeaponTier.COMMON: 0.82, WeaponTier.UNCOMMON: 1.0, WeaponTier.RARE: 1.18, WeaponTier.LEGENDARY: 1.4}
TIER_LEVEL = {WeaponTier.COMMON: Level.LOW, WeaponTier.UNCOMMON: Level.MEDIUM, WeaponTier.RARE: Level.HIGH,
              WeaponTier.LEGENDARY: Level.LEGENDARY}
PRESETS = {
    "Easy": (0.3, 0.35, 0.25, 0.1),
    "Standard": (0.4, 0.35, 0.2, 0.05),
    "Hard": (0.55, 0.3, 0.12, 0.03),
    "Misery": (0.7, 0.22, 0.07, 0.01),
}

FISTS = 900000
CATALYSTS, ARROWS, BOLTS, SHIELDS = 8, 13, 14, 12
MAGIC_FLAGS = ("enableMagic", "enableSorcery", "enableMiracle", "enableVowMagic")
CLASSES = range(3000, 3010)
CLASS_SLOTS = ("equip_Wep_Right", "equip_Subwep_Right", "equip_Wep_Left", "equip_Subwep_Left")

DAMAGE = ("attackBasePhysics", "attackBaseMagic", "attackBaseFire", "attackBaseThunder")
ELEMENTS = ("attackBaseMagic", "attackBaseFire", "attackBaseThunder")
PHYSICAL_SCALING = ("correctStrength", "correctAgility")
MAGIC_SCALING = ("correctMagic", "correctFaith")
SCALING = PHYSICAL_SCALING + MAGIC_SCALING
REQUIREMENTS = {"correctStrength": "properStrength", "correctAgility": "properAgility",
                "correctMagic": "properMagic", "correctFaith": "properFaith"}
GUARD_CUTS = ("physGuardCutRate", "magGuardCutRate", "fireGuardCutRate", "thunGuardCutRate")
STATUS_GUARD = ("poisonGuardResist", "diseaseGuardResist", "bloodGuardResist", "curseGuardResist")
ON_HIT = ("spEffectBehaviorId0", "spEffectBehaviorId1", "spEffectBehaviorId2")
WHILE_HELD = ("residentSpEffectId", "residentSpEffectId1", "residentSpEffectId2")
MOVESET = ("wepmotionOneHandId", "wepmotionBothHandId", "spAtkcategory", "behaviorVariationId")

NEGLIGIBLE = 0.1  # damage share below which a damage type gets no scaling
REFERENCE_SCALING = 0.5  # stat curve value at reference stats (roughly 30 in a stat)
MAX_SCALING = 150.0
MAX_REQUIREMENT = 60
SCALED_REQUIREMENT = (40, 8)  # scaling at or above [0] needs at least [1] + scaling / 10 in that stat

WEAPON_WEIGHTS = {"offense": 0.55, "weight": 0.15, "requirements": 0.12, "guard": 0.08}
SHIELD_WEIGHTS = {"offense": 0.1, "weight": 0.2, "requirements": 0.1, "guard": 0.6}
CANDIDATES = 48

# On-hit effects: kind -> (vanilla template SpEffect, amount field, sign, amounts per level, text).
ON_HIT_KINDS = {
    "bleed": (6400, "registBlood", 1, (20, 30, 45, 60), "Bleed +{amount}"),
    "poison": (6500, "poizonAttackPower", 1, (20, 30, 45, 60), "Poison +{amount}"),
    "toxic": (6600, "registIllness", 1, (15, 25, 35, 50), "Toxic +{amount}"),
    "hp_on_hit": (6730, "changeHpPoint", -1, (3, 5, 8, 12), "Restores {amount} HP per hit"),
}
LEVEL_INDEX = {Level.LOW: 0, Level.MEDIUM: 1, Level.HIGH: 2, Level.LEGENDARY: 3}
# Passive fields that only make sense next to other ring effects (e.g. "effects activate at 50% HP").
STANDALONE_EXCLUDED = frozenset({"conditionHp"})
EFFECT_VALUE = {Level.NEGATIVE: -0.08, Level.LOW: 0.04, Level.MEDIUM: 0.08, Level.HIGH: 0.12, Level.LEGENDARY: 0.16}


@dataclass
class WeaponConfig:
    tier_weights: tuple[float, float, float, float] = PRESETS["Standard"]
    weapons: bool = True
    shields: bool = True
    moveset_chance: float = 0.25
    effect_chance: float = 0.25
    element_chance: float = 0.15
    isolate_npcs: bool = True
    write_descriptions: bool = True
    pinned: frozenset[int] = frozenset({FISTS})


@dataclass
class WeaponResult:
    weapon_id: int
    tier: WeaponTier
    shield: bool
    value: float = 0.0  # achieved value (1.0 = as vanilla)
    changes: dict[str, object] = field(default_factory=dict)
    moveset_from: int | None = None
    effects: list[str] = field(default_factory=list)
    capped_for_class: bool = False


def is_pinned(weapon_id: int, values: dict, pinned=frozenset({FISTS})) -> bool:
    return (weapon_id in pinned or values["weaponCategory"] in (CATALYSTS, ARROWS, BOLTS)
            or any(values[f] for f in MAGIC_FLAGS) or bool(values["lanternWep"]) or bool(values["isDarkHand"]))


def offense(values: dict) -> float:
    """Attack rating at reference stats."""
    physical, magic = values["attackBasePhysics"], values["attackBaseMagic"]
    total = sum(values[f] for f in DAMAGE)
    total += physical * sum(values[f] for f in PHYSICAL_SCALING) / 100 * REFERENCE_SCALING
    total += magic * sum(values[f] for f in MAGIC_SCALING) / 100 * REFERENCE_SCALING
    return total


def guard(values: dict) -> float:
    elemental = sum(values[f] for f in GUARD_CUTS[1:]) / 3
    return 0.5 * values["physGuardCutRate"] + 0.2 * elemental + 0.3 * values["staminaGuardDef"] \
        + 0.05 * sum(values[f] for f in STATUS_GUARD) / 4


def requirements(values: dict) -> float:
    return sum(values[f] for f in REQUIREMENTS.values())


def value(new: dict, old: dict, shield: bool, effects: float = 0.0) -> float:
    """Log value of `new` relative to `old` (0 = as good as vanilla)."""
    weights = SHIELD_WEIGHTS if shield else WEAPON_WEIGHTS
    ratios = {
        "offense": (offense(new) + 10) / (offense(old) + 10),
        "weight": (old["weight"] + 1) / (new["weight"] + 1),
        "requirements": (requirements(old) + 10) / (requirements(new) + 10),
        "guard": (guard(new) + 10) / (guard(old) + 10),
    }
    return sum(weights[k] * math.log(r) for k, r in ratios.items()) + effects


def scalable_stats(values: dict) -> tuple[str, ...]:
    total = sum(values[f] for f in DAMAGE) or 1
    stats = ()
    if values["attackBasePhysics"] / total > NEGLIGIBLE:
        stats += PHYSICAL_SCALING
    if values["attackBaseMagic"] / total > NEGLIGIBLE:
        stats += MAGIC_SCALING
    return stats


def _log_uniform(rng: random.Random, low: float, high: float) -> float:
    return math.exp(rng.uniform(math.log(low), math.log(high)))


class _WeaponBuilder:
    def __init__(self, session: Session, config: WeaponConfig, rng: random.Random):
        self.session = session
        self.config = config
        self.rng = rng
        self.weapons = session.base.params["EquipParamWeapon"]
        self.template = passive_template(session)
        limits = reference_limits(session.base)["SpEffectParam"]
        self.speffect_max = {f: limits.get(("EquipParamWeapon", f), 2**31 - 1) for f in ON_HIT + WHILE_HELD}
        self.class_caps = self._class_caps()
        self.movesets = self._movesets()

    def _class_caps(self) -> dict[int, dict[str, int]]:
        """Starting weapon / shield row -> the lowest stats among the classes starting with it."""
        chara = self.session.base.params["CharaInitParam"]
        caps: dict[int, dict[str, int]] = {}
        stats = {"properStrength": "baseStr", "properAgility": "baseDex", "properMagic": "baseMag",
                 "properFaith": "baseFai"}
        for class_id in CLASSES:
            if class_id not in chara.rows:
                continue
            row = chara.row_values(class_id)
            for slot in CLASS_SLOTS:
                weapon = row[slot] - row[slot] % 100 if row[slot] > 0 else -1
                if weapon in self.weapons.rows:
                    cap = caps.setdefault(weapon, {f: 99 for f in stats})
                    for requirement, stat in stats.items():
                        cap[requirement] = min(cap[requirement], row[stat])
        return caps

    def _movesets(self) -> dict[tuple[int, int], list[int]]:
        """(weapon category, animation set) -> named base weapons with a distinct moveset (unnamed rows are unused)."""
        names = self.session.base.text.get(11, ("", {}))[1]
        groups: dict[tuple[int, int], dict[tuple, int]] = defaultdict(dict)
        for weapon_id in sorted(self.weapons.rows):
            values = self.weapons.row_values(weapon_id)
            if weapon_id % 1000 or is_pinned(weapon_id, values, self.config.pinned) or not names.get(weapon_id):
                continue
            key = (values["weaponCategory"], values["wepmotionCategory"])
            groups[key].setdefault(tuple(values[f] for f in MOVESET), weapon_id)
        return {key: sorted(sets.values()) for key, sets in groups.items() if len(sets) > 1}

    def moveset_for(self, family: int) -> int | None:
        values = self.weapons.row_values(family)
        options = [w for w in self.movesets.get((values["weaponCategory"], values["wepmotionCategory"]), [])
                   if tuple(self.weapons.row_values(w)[f] for f in MOVESET) != tuple(values[f] for f in MOVESET)]
        if options and self.rng.random() < self.config.moveset_chance:
            return self.rng.choice(options)
        return None

    def candidate(self, old: dict, shield: bool) -> dict:
        rng = self.rng
        new = dict(old)
        if shield:
            new["physGuardCutRate"] = float(min(100, max(0, round(old["physGuardCutRate"] + rng.uniform(-15, 15)))))
            for name in GUARD_CUTS[1:]:
                new[name] = float(min(100, round(old[name] * _log_uniform(rng, 0.6, 1.6))))
            new["staminaGuardDef"] = max(1, round(old["staminaGuardDef"] * _log_uniform(rng, 0.75, 1.35)))
            for name in STATUS_GUARD:
                new[name] = min(100, round(old[name] * _log_uniform(rng, 0.6, 1.5)))
            damage = _log_uniform(rng, 0.8, 1.25)
        else:
            for name in GUARD_CUTS:
                new[name] = float(min(100, round(old[name] * _log_uniform(rng, 0.85, 1.15))))
            damage = _log_uniform(rng, 0.65, 1.55)
        for name in DAMAGE:
            new[name] = round(old[name] * damage)
        if not shield and new["attackBasePhysics"] > 0 and rng.random() < self.config.element_chance:
            element = rng.choice(ELEMENTS)
            moved = round(new["attackBasePhysics"] * rng.uniform(0.25, 0.6))
            new["attackBasePhysics"] -= moved
            new[element] += moved
        self._scaling(old, new)
        for scaling, requirement in REQUIREMENTS.items():
            req = round(old[requirement] * _log_uniform(rng, 0.6, 1.45))
            if new[scaling] >= SCALED_REQUIREMENT[0]:
                req = max(req, SCALED_REQUIREMENT[1] + round(new[scaling] / 10))
            new[requirement] = min(MAX_REQUIREMENT, req)
        new["weight"] = max(0.5, round(old["weight"] * _log_uniform(rng, 0.7, 1.4) * 2) / 2) if old["weight"] else 0.0
        return new

    def _scaling(self, old: dict, new: dict) -> None:
        rng = self.rng
        stats = scalable_stats(new)
        total = sum(old[f] for f in SCALING)
        if not total and stats and rng.random() < 0.25:
            total = rng.uniform(30, 90)
        total *= _log_uniform(rng, 0.55, 1.8)
        for name in SCALING:
            new[name] = 0.0
        if not stats or total <= 0:
            return
        weights = {s: rng.gammavariate(0.6, 1.0) for s in stats}
        norm = sum(weights.values()) or 1.0
        for name, weight in weights.items():
            new[name] = float(min(MAX_SCALING, round(total * weight / norm)))

    def effects(self, tier: WeaponTier, shield: bool) -> tuple[list[tuple[str, object]], float]:
        """Effects to add: ("on_hit", kind) / ("held", (values, summaries)) with their total value. Shields only get
        while-held effects (they hit with bashes only)."""
        rng, level = self.rng, TIER_LEVEL[tier]
        chosen, total = [], 0.0
        if rng.random() < self.config.effect_chance and not shield:
            chosen.append(("on_hit", (rng.choice(list(ON_HIT_KINDS)), level)))
            total += EFFECT_VALUE[level]
        if rng.random() < self.config.effect_chance:
            held = Level.NEGATIVE if tier == WeaponTier.COMMON and rng.random() < 0.3 else level
            values, summaries = roll_passive(rng, (held,), max_effects=2, exclude=STANDALONE_EXCLUDED)
            if summaries:
                chosen.append(("held", (values, summaries)))
                total += EFFECT_VALUE[held]
        return chosen, total

    def apply_effects(self, weapon_id: int, new: dict, chosen) -> list[str]:
        texts = []
        for kind, payload in chosen:
            slots = ON_HIT if kind == "on_hit" else WHILE_HELD
            slot = next((s for s in slots if new[s] <= 0), None)
            if slot is None:
                continue
            speffect = self.session.ids.allocate("SpEffectParam", self.speffect_max[slot])
            if kind == "on_hit":
                status, level = payload
                template, amount_field, sign, amounts, text = ON_HIT_KINDS[status]
                amount = amounts[LEVEL_INDEX[level]]
                self.session.store.add("SpEffectParam", speffect, copy_from=template)
                self.session.store.set("SpEffectParam", speffect, {amount_field: sign * amount})
                texts.append(text.format(amount=amount))
            else:
                values, summaries = payload
                self.session.store.add("SpEffectParam", speffect, copy_from=self._template_row())
                self.session.store.set("SpEffectParam", speffect, {**self.template, **values})
                texts.append("While held: " + ", ".join(summaries))
            new[slot] = speffect
        return texts

    def _template_row(self) -> int:
        rings = self.session.base.params["EquipParamAccessory"]
        return rings.row_values(min(r for r in rings.rows if r))["refId"]

    def build(self, weapon_id: int, moveset_from: int | None) -> WeaponResult:
        rng = self.rng
        old = self.weapons.row_values(weapon_id)
        shield = old["weaponCategory"] == SHIELDS
        tier = WeaponTier(rng.choices(range(len(WeaponTier)), weights=self.config.tier_weights)[0])
        chosen, effect_value = self.effects(tier, shield)
        target = math.log(TIER_VALUE[tier])
        best, best_score = None, None
        for _ in range(CANDIDATES):
            new = self.candidate(old, shield)
            cap = self.class_caps.get(weapon_id)
            if cap:
                for requirement, limit in cap.items():
                    new[requirement] = min(new[requirement], limit)
            score = abs(value(new, old, shield, effect_value) - target)
            if best_score is None or score < best_score:
                best, best_score = new, score
        result = WeaponResult(weapon_id, tier, shield, capped_for_class=weapon_id in self.class_caps)
        if moveset_from is not None:
            source = self.weapons.row_values(moveset_from)
            best.update({f: source[f] for f in MOVESET})
            result.moveset_from = moveset_from
        result.effects = self.apply_effects(weapon_id, best, chosen)
        result.value = math.exp(value(best, old, shield, effect_value))
        result.changes = {f: best[f] for f in best if best[f] != old[f]}
        self.session.store.set("EquipParamWeapon", weapon_id, result.changes)
        return result


def describe(result: WeaponResult, long_desc: str | None, moveset_name: str | None) -> str | None:
    """The weapon's long description with rarity, moveset and effect lines after its type / attack type lines."""
    if long_desc is None:
        return None
    lines = [f"Rarity: {result.tier.name.title()}"]
    if moveset_name:
        lines.append(f"Moveset: {moveset_name}")
    lines += result.effects
    head, sep, rest = long_desc.partition("\n\n")
    if not sep:
        return "\n".join(lines) + "\n\n" + long_desc
    return head + "\n" + "\n".join(lines) + "\n\n" + rest


def randomize_weapons(session: Session, config: WeaponConfig, rng: random.Random) -> list[WeaponResult]:
    weapons = session.base.params["EquipParamWeapon"]
    if config.isolate_npcs:
        params = {"EquipParamWeapon"}
        session.allocate(["player_weapon", "enemy"], params=params, rows=session.footprint("player_weapon", params))
    builder = _WeaponBuilder(session, config, rng)
    names = session.base.text.get(11, ("", {}))[1]
    long_descs = session.base.text.get(25, ("", {}))[1]
    families: dict[int, int | None] = {}
    results = []
    for weapon_id in sorted(weapons.rows):
        values = weapons.row_values(weapon_id)
        if is_pinned(weapon_id, values, config.pinned):
            continue
        shield = values["weaponCategory"] == SHIELDS
        if (shield and not config.shields) or (not shield and not config.weapons):
            continue
        family = weapon_id - weapon_id % 1000
        if family not in families:
            families[family] = builder.moveset_for(family if family in weapons.rows else weapon_id)
        result = builder.build(weapon_id, families[family])
        if config.write_descriptions:
            moveset_name = names.get(result.moveset_from) if result.moveset_from else None
            text = describe(result, long_descs.get(weapon_id) or None, moveset_name)
            if text:
                session.text[("Weapon_long_desc", weapon_id)] = text
        results.append(result)
    return results
