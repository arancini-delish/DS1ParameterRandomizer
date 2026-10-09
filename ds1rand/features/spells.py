"""Spell randomizer (Phase 6.2).

Every spell keeps its school and cast animation category (`catalogue.subtypes`): a sorcery projectile stays a sorcery
projectile, a pyromancy mist stays a mist, so the cast animation always fits what it fires. What changes:

    payload   a donor spell of the same category (and delivery: bullet or SpEffect) is drawn; its bullet chain (or its
              SpEffect) is copied into new rows for this spell, so e.g. Soul Arrow may fire a Soul Spear or a Homing
              Soulmass; sorcery projectiles may take a charged-cast donor's payload too
    visuals   with `visual_chance`, the root bullet takes another spell's projectile / impact / repel particles
              (same school by default)
    status    with `status_chance`, the last damaging bullet also applies an on-hit status effect (poison, bleed, ...)
              drawn from those vanilla spells and weapons use
    power     a tier (Weak / Standard / Strong / Legendary) and costs drawn from what the category uses in vanilla;
              damage and effect magnitudes are the donor's, scaled by the power factor

Power factor = tier power x casts factor x slots factor x requirement factor x cast factor (clamped to
`POWER_LIMITS`), where the casts factor
compares the prototype's usage curve (`USAGE_CURVE`) at the new and the donor's cast count: fewer casts, more power.
Two slots, a higher stat requirement or upgrading a sorcery projectile to the slower charged cast also add power. This
keeps the base game's curve: stronger spells cost more casts, slots, stats or cast time.

NPC caster copies of spells (Magic 13xxx, used through CharaInitParam) can be randomized the same way, without costs
(NPCs cast without limits). All copies are new rows: root bullets / SpEffects in the narrow ID block (Magic.refId is
s16), everything else in the wide block; no spell shares rows with another afterwards. Spell bullets look up attacks in
AtkParam_Pc for every caster (NPC spell bullets' attacks only exist there), so attack copies go to AtkParam_Pc.
Utility spells with custom engine behaviour are pinned (`DEFAULT_PINNED`).
"""
from __future__ import annotations

import bisect
import math
import random
from collections import Counter
from dataclasses import dataclass, field
from enum import IntEnum

from ds1rand.catalogue.effects import EffectClassifier
from ds1rand.catalogue.subtypes import CAST_ANIMATIONS, SCHOOLS, bullet_chain
from ds1rand.graph.model import Node
from ds1rand.session import Session

S16_MAX = 32767


class SpellTier(IntEnum):
    WEAK = 0
    STANDARD = 1
    STRONG = 2
    LEGENDARY = 3


TIER_POWER = {SpellTier.WEAK: 0.8, SpellTier.STANDARD: 1.0, SpellTier.STRONG: 1.25, SpellTier.LEGENDARY: 1.5}
PRESETS = {
    "Easy": (0.15, 0.45, 0.3, 0.1),
    "Standard": (0.25, 0.5, 0.2, 0.05),
    "Hard": (0.4, 0.45, 0.12, 0.03),
    "Misery": (0.55, 0.38, 0.06, 0.01),
}

# Prototype usage curve: casts -> relative power per cast (few casts: strong casts). Continuous spells (sprays,
# whips, sword dances; vanilla casts >= 40) use their own curve.
USAGE_CURVE = ((1, 3.0), (2, 2.0), (3, 1.5), (4, 1.25), (5, 1.125), (6, 1.1), (8, 1.0), (10, 0.95), (12, 0.9),
               (16, 0.8), (20, 0.73), (24, 0.64), (30, 0.5))
CONTINUOUS_USAGE_CURVE = ((40, 2.0), (60, 1.5), (80, 1.0), (100, 0.8), (120, 0.6), (160, 0.4))
TWO_SLOT_POWER = 1.25
CHARGED_CAST_POWER = 1.2
REQUIREMENT_POWER_PER_POINT = 0.02
STATUS_DAMAGE_COST = 0.9  # a spell that also applies a status hits a little softer
POWER_LIMITS = (0.4, 2.5)  # final power factor range

# Cast categories whose spells may swap payloads (sorcery projectiles: normal and charged casts).
FAMILIES = {"projectile": "projectile", "projectile_charged": "projectile"}

# Spells with custom engine behaviour or a utility role, left alone.
DEFAULT_PINNED = frozenset({
    3410, 3500, 3510, 3520, 3530, 3540, 3550, 3600, 3610,  # Hidden Body, Cast Light, Hush, Aural Decoy, Repair,
                                                            # Fall Control, Chameleon, Resist Curse, Remedy
    4360,  # Undead Rapport
    5200, 5210, 5400, 5700, 5800, 5810,  # Escape Death, Homeward, Seek Guidance, Karmic Justice, Tranquil Walk,
                                         # Vow of Silence
})

DAMAGE_FIELDS = ("atkPhys", "atkMag", "atkFire", "atkThun")
SCALED_GROUPS = ("attack", "defense", "regen", "max_stats")


def usage_power(casts: int, continuous: bool) -> float:
    """Relative power per cast at `casts` (interpolated on log casts)."""
    curve = CONTINUOUS_USAGE_CURVE if continuous else USAGE_CURVE
    xs = [math.log(c) for c, _ in curve]
    x = math.log(max(casts, 1))
    if x <= xs[0]:
        return curve[0][1]
    if x >= xs[-1]:
        return curve[-1][1]
    i = bisect.bisect_right(xs, x)
    t = (x - xs[i - 1]) / (xs[i] - xs[i - 1])
    return curve[i - 1][1] + t * (curve[i][1] - curve[i - 1][1])


@dataclass
class SpellConfig:
    tier_weights: tuple[float, float, float, float] = PRESETS["Standard"]
    player: bool = True
    enemy: bool = True
    pinned: frozenset[int] = DEFAULT_PINNED
    visual_chance: float = 0.5
    cross_school_visuals: bool = False
    status_chance: float = 0.15
    two_slot_chance: float = 0.15
    charged_upgrade_chance: float = 0.5
    write_summaries: bool = True


@dataclass
class SpellResult:
    magic_id: int
    owner: str  # "player" or "enemy"
    tier: SpellTier
    donor: int
    cast: str
    casts: int
    slots: int
    requirement: int
    power: float
    root: int  # new root bullet or SpEffect
    visual_from: int | None = None
    status: int | None = None
    summary: str = ""
    rows: Counter = field(default_factory=Counter)  # new rows per param


class _SpellBuilder:
    def __init__(self, session: Session, config: SpellConfig, rng: random.Random):
        self.session = session
        self.base = session.base
        self.store = session.store
        self.ids = session.ids
        self.config = config
        self.rng = rng
        self.magic = self.base.params["Magic"]
        self.classifier = EffectClassifier(self.base, session.graph)
        self.player_spells = sorted(n.id for n in session.footprint("player_spell", {"Magic"}))
        self.enemy_spells = sorted(n.id for n in session.footprint("enemy", {"Magic"}) if n.id not in self.player_spells)
        self.vanilla = {m: self.magic.row_values(m) for m in self.player_spells + self.enemy_spells}
        self.status_pool = self._status_pool()

    # Pools

    def family(self, magic_id: int) -> str:
        cast = CAST_ANIMATIONS.get(self.vanilla[magic_id]["refType"], "unknown")
        return FAMILIES.get(cast, cast)

    def donors(self, magic_id: int) -> list[int]:
        """Same category, delivery and school, from the same owner group (player spells for player spells, NPC copies
        for NPC spells: their damage and casts are tuned differently)."""
        v = self.vanilla[magic_id]
        group = self.player_spells if magic_id in self.player_spells else self.enemy_spells
        return [m for m in group
                if self.family(m) == self.family(magic_id) and self.vanilla[m]["refCategory"] == v["refCategory"]
                and self.vanilla[m]["ezStateBehaviorType"] == v["ezStateBehaviorType"] and m not in self.config.pinned]

    def visuals(self, magic_id: int) -> list[int]:
        school = self.vanilla[magic_id]["ezStateBehaviorType"]
        return [m for m in self.player_spells
                if self.vanilla[m]["refCategory"] == 1 and m not in self.config.pinned
                and (self.config.cross_school_visuals or self.vanilla[m]["ezStateBehaviorType"] == school)
                and self.base.params["Bullet"].row_values(self.vanilla[m]["refId"])["sfxId_Bullet"] > 0]

    def _status_pool(self) -> list[int]:
        used = set()
        for name in ("Bullet", "AtkParam_Pc"):
            pb = self.base.params[name]
            for row_id in pb.rows:
                values = pb.row_values(row_id)
                used.update(values[f"spEffectId{i}"] for i in range(5) if values[f"spEffectId{i}"] > 0)
        speffects = self.base.params["SpEffectParam"].rows
        return sorted(s for s in used if s in speffects and self.classifier.speffect(s).kind == "status")

    def category_values(self, magic_id: int, field_name: str) -> list[int]:
        family = self.family(magic_id)
        return sorted({self.vanilla[m][field_name] for m in self.player_spells
                       if self.family(m) == family and self.vanilla[m][field_name] > 0})

    # Building

    def build(self, magic_id: int, owner: str) -> SpellResult:
        rng = self.rng
        v = self.vanilla[magic_id]
        tier = SpellTier(rng.choices(range(len(SpellTier)), weights=self.config.tier_weights)[0])
        donor = rng.choice(self.donors(magic_id))
        d = self.vanilla[donor]
        power = TIER_POWER[tier]
        updates = {"refId": 0}
        casts, slots, requirement = v["maxQuantity"], v["slotLength"], 0
        cast_type = v["refType"]

        if owner == "player":
            continuous = max(self.category_values(magic_id, "maxQuantity") or [1]) >= 40
            casts = rng.choice(self.category_values(magic_id, "maxQuantity") or [d["maxQuantity"]])
            power *= usage_power(casts, continuous) / usage_power(max(d["maxQuantity"], 1), continuous)
            slots = 2 if rng.random() < self.config.two_slot_chance else 1
            power *= TWO_SLOT_POWER if slots == 2 else 1.0
            school = SCHOOLS.get(v["ezStateBehaviorType"])
            req_field = {"sorcery": "requirementIntellect", "miracle": "requirementFaith"}.get(school)
            if req_field:
                requirement = rng.choice(self.category_values(magic_id, req_field) or [d[req_field]])
                factor = 1 + REQUIREMENT_POWER_PER_POINT * (requirement - d[req_field])
                power *= min(max(factor, 0.7), 1.5)
                updates[req_field] = requirement
            if (CAST_ANIMATIONS.get(cast_type) == "projectile" and tier >= SpellTier.STRONG
                    and rng.random() < self.config.charged_upgrade_chance):
                cast_type = next(k for k, name in CAST_ANIMATIONS.items() if name == "projectile_charged")
                power *= CHARGED_CAST_POWER
            updates.update(maxQuantity=casts, slotLength=slots, refType=cast_type)

        power = min(max(power, POWER_LIMITS[0]), POWER_LIMITS[1])
        result = SpellResult(magic_id, owner, tier, donor, CAST_ANIMATIONS.get(cast_type, "?"), casts, slots,
                             requirement, power, 0)
        if d["refCategory"] == 1:
            result.root = self._copy_chain(d["refId"], power, result)
        else:
            result.root = self._copy_speffect(d["refId"], power, result, root=True)
        updates["refId"] = result.root
        updates["refCategory"] = d["refCategory"]
        self.store.set("Magic", magic_id, updates)
        result.summary = self._summary(result)
        return result

    def _copy_chain(self, root: int, power: float, result: SpellResult) -> int:
        chain = bullet_chain(self.base, root)
        new_ids = {}
        for i, bullet in enumerate(chain):
            new_ids[bullet] = self.ids.allocate("Bullet", S16_MAX if i == 0 else 2**31 - 1)
            self.store.add("Bullet", new_ids[bullet], copy_from=bullet)
            result.rows["Bullet"] += 1

        status_added = False
        if self.status_pool and self.rng.random() < self.config.status_chance:
            result.status = self.rng.choice(self.status_pool)
            power *= STATUS_DAMAGE_COST
        damaging = [b for b in chain if self.base.params["Bullet"].row_values(b)["atkId_Bullet"] > 0]

        for bullet in chain:
            values = self.base.params["Bullet"].row_values(bullet)
            updates = {}
            if values["HitBulletID"] in new_ids:
                updates["HitBulletID"] = new_ids[values["HitBulletID"]]
            if values["atkId_Bullet"] > 0 and values["atkId_Bullet"] in self.base.params["AtkParam_Pc"].rows:
                updates["atkId_Bullet"] = self._copy_attack(values["atkId_Bullet"], power, result)
            for name in ["spEffectIDForShooter"] + [f"spEffectId{i}" for i in range(5)]:
                if values[name] > 0 and self._scalable(values[name]):
                    updates[name] = self._copy_speffect(values[name], power, result)
            if result.status and not status_added and damaging and bullet == damaging[-1]:
                free = next((f"spEffectId{i}" for i in range(5) if values[f"spEffectId{i}"] <= 0), None)
                if free:
                    updates[free] = result.status
                    status_added = True
            if updates:
                self.store.set("Bullet", new_ids[bullet], updates)
        if result.status and not status_added:
            result.status = None

        if self.rng.random() < self.config.visual_chance:
            source = self.rng.choice(self.visuals(result.magic_id) or [result.donor])
            sfx = self.base.params["Bullet"].row_values(self.vanilla[source]["refId"])
            self.store.set("Bullet", new_ids[root], {f: sfx[f] for f in ("sfxId_Bullet", "sfxId_Hit", "sfxId_Flick")})
            result.visual_from = source
        return new_ids[root]

    def _copy_attack(self, attack: int, power: float, result: SpellResult) -> int:
        values = self.base.params["AtkParam_Pc"].row_values(attack)
        new_id = self.ids.allocate("AtkParam_Pc")
        self.store.add("AtkParam_Pc", new_id, copy_from=attack)
        self.store.set("AtkParam_Pc", new_id, {f: int(round(values[f] * power)) for f in DAMAGE_FIELDS if values[f]})
        result.rows["AtkParam_Pc"] += 1
        return new_id

    def _scalable(self, speffect: int) -> bool:
        if speffect not in self.base.params["SpEffectParam"].rows:
            return False
        if speffect in self.store.protected.get("SpEffectParam", set()):
            return False
        effect = self.classifier.speffect(speffect)
        return effect.state is None and bool(set(effect.groups) & set(SCALED_GROUPS))

    def _copy_speffect(self, speffect: int, power: float, result: SpellResult, root: bool = False) -> int:
        new_id = self.ids.allocate("SpEffectParam", S16_MAX if root else 2**31 - 1)
        self.store.add("SpEffectParam", new_id, copy_from=speffect)
        result.rows["SpEffectParam"] += 1
        values = self.base.params["SpEffectParam"].row_values(speffect)
        neutral = self.classifier.neutral
        from ds1rand.catalogue.effects import GROUP_FIELDS

        scaled = {}
        for group in SCALED_GROUPS:
            for name in GROUP_FIELDS[group]:
                value, base = values[name], neutral[name]
                if value == base:
                    continue
                if isinstance(base, float) and base == 1.0:
                    scaled[name] = 1.0 + (value - 1.0) * power
                elif isinstance(value, float):
                    scaled[name] = value * power
                else:
                    scaled[name] = int(round(value * power))
        if scaled:
            self.store.set("SpEffectParam", new_id, scaled)
        return new_id

    def _summary(self, result: SpellResult) -> str:
        parts = [result.tier.name.title()]
        if result.owner == "player":
            parts.append(f"{result.casts} cast{'s' if result.casts != 1 else ''}"
                         + (", 2 slots" if result.slots == 2 else ""))
        if result.status:
            parts.append("inflicts status")
        return " - ".join(parts)


def randomize_spells(session: Session, config: SpellConfig, rng: random.Random) -> list[SpellResult]:
    builder = _SpellBuilder(session, config, rng)
    results = []
    for owner, spells, enabled in (("player", builder.player_spells, config.player),
                                   ("enemy", builder.enemy_spells, config.enemy)):
        if not enabled:
            continue
        for magic_id in spells:
            if magic_id in config.pinned or not builder.donors(magic_id):
                continue
            result = builder.build(magic_id, owner)
            if owner == "player" and config.write_summaries:
                session.text[("Magic_description", magic_id)] = result.summary
            results.append(result)
    return results
