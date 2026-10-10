"""Building randomized bullet chains, shared by the spell and projectile randomizers.

`ChainBuilder.build` copies a donor bullet chain into new rows (root in the narrow ID block when a 16-bit field will
reference it) and, by chance:
    motion    moving root bullets (linear, homing, lobbed) get a new speed (x0.6-1.6) and homing strength, or homing
              added to straight shots; faster and homing shots cost power
    chain     the end of the chain spawns another chain from the feature's chain pool (up to MAX_CHAIN bullets); the
              parent keeps CHAINED_PARENT_POWER of its power, the child gets CHILD_POWER of it
    status    the last damaging bullet also applies a status effect from the status pool, at STATUS_DAMAGE_COST
    visuals   the root takes the particles of a bullet from the feature's visual pool; sometimes a later bullet too
Attacks are copied into the feature's attack table and scaled by the power factor (a donor fired by the other side
reads its attacks from its own table: player and spell bullets use AtkParam_Pc, enemy and trap bullets AtkParam_Npc); SpEffects with numeric payloads
(attack, defense, regen, max stats) are copied and scaled too. The outcome (final power, motion, chained source, child
power, status, visual source, new rows per param) is written onto the result object passed in.

Pools hold (tag, bullet) pairs; the tag identifies the source for reports (a Magic ID for spells, a bullet ID for
projectiles).
"""
from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from ds1rand.catalogue.effects import GROUP_FIELDS, EffectClassifier
from ds1rand.catalogue.subtypes import bullet_chain, classify_bullet
from ds1rand.session import Session

S16_MAX = 32767
DAMAGE_FIELDS = ("atkPhys", "atkMag", "atkFire", "atkThun")
CORRECTION_FIELDS = ("atkPhysCorrection", "atkMagCorrection", "atkFireCorrection", "atkThunCorrection")
SCALED_GROUPS = ("attack", "defense", "regen", "max_stats")
STATUS_DAMAGE_COST = 0.9

SPEED_FIELDS = ("initVellocity", "maxVellocity", "minVellocity", "accelInRange", "accelOutRange")
SPEED_RANGE = (0.6, 1.6)
SPEED_POWER_COST = 0.15  # per 1.0 of speed factor above (or refund below) 1
HOMING_RANGE = (0.5, 2.0)
ADD_HOMING_CHANCE = 0.3
ADDED_HOMING_ANGLE = (2, 8)
ADDED_HOMING_POWER = 0.9

MAX_CHAIN = 6
CHAINED_PARENT_POWER = 0.8
CHILD_POWER = 0.5


@dataclass
class ChainOptions:
    visual_chance: float = 0.0
    motion_chance: float = 0.0
    chain_chance: float = 0.0
    status_chance: float = 0.0


def status_pool(session: Session, classifier: EffectClassifier) -> list[int]:
    """Status SpEffects (poison, toxic, bleed, curse...) that vanilla bullets and attacks apply on hit."""
    used = set()
    for name in ("Bullet", "AtkParam_Pc", "AtkParam_Npc"):
        pb = session.base.params[name]
        for row_id in pb.rows:
            values = pb.row_values(row_id)
            used.update(values[f"spEffectId{i}"] for i in range(5) if values[f"spEffectId{i}"] > 0)
    speffects = session.base.params["SpEffectParam"].rows
    return sorted(s for s in used if s in speffects and classifier.speffect(s).kind == "status")


def chain_candidates(session: Session, pairs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Bullets fit to be spawned at the end of another chain: not orbiting or attached (they need their owner) and not
    streams (one child per particle)."""
    bullets = session.base.params["Bullet"]
    pool, seen = [], set()
    for tag, bullet in pairs:
        cls = classify_bullet(bullets.row_values(bullet))
        if bullet in seen or cls.motion in ("orbit", "attached") or "stream" in cls.qualifiers:
            continue
        seen.add(bullet)
        pool.append((tag, bullet))
    return pool


def visual_candidates(session: Session, pairs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """One entry per distinct visible particle set."""
    bullets = session.base.params["Bullet"]
    pool, seen = [], set()
    for tag, bullet in pairs:
        values = bullets.row_values(bullet)
        key = (values["sfxId_Bullet"], values["sfxId_Hit"], values["sfxId_Flick"])
        if values["sfxId_Bullet"] > 0 and key not in seen:
            seen.add(key)
            pool.append((tag, bullet))
    return pool


class ChainBuilder:
    def __init__(self, session: Session, rng: random.Random, classifier: EffectClassifier | None = None):
        self.session = session
        self.base = session.base
        self.store = session.store
        self.ids = session.ids
        self.rng = rng
        self.classifier = classifier or EffectClassifier(self.base, session.graph)
        self.status_pool = status_pool(session, self.classifier)
        self._attack_source: Callable[[int], str] | None = None

    def build(
        self,
        donor_root: int,
        power: float,
        result,
        *,
        attack_param: str,
        options: ChainOptions,
        visual_pool: list[tuple[int, int]],
        chain_pool: list[tuple[int, int]],
        narrow_root: bool,
        limits: tuple[float, float] | None = None,
        attack_source: Callable[[int], str] | None = None,
    ) -> int:
        """Copy the chain at `donor_root` for `result`; returns the new root bullet. `attack_source` gives the attack
        table a donor bullet's `atkId_Bullet` refers to (default: `attack_param`)."""
        rng = self.rng
        self._attack_source = attack_source
        clamp = (lambda p: min(max(p, limits[0]), limits[1])) if limits else (lambda p: p)
        chain = bullet_chain(self.base, donor_root)
        root_class = classify_bullet(self.base.params["Bullet"].row_values(donor_root))

        # Decide motion and chained effects first: both move power around.
        own_power = power
        motion = self._motion(donor_root, root_class, options, result)
        if motion:
            power *= motion.pop("_power")
        child = None
        if (chain_pool and "stream" not in root_class.qualifiers and len(chain) <= MAX_CHAIN
                and rng.random() < options.chain_chance):
            child = rng.choice(chain_pool)
            result.chained_from = child
            power *= CHAINED_PARENT_POWER
        if self.status_pool and rng.random() < options.status_chance:
            result.status = rng.choice(self.status_pool)
            power *= STATUS_DAMAGE_COST
        power = clamp(power)
        result.power = power

        new_ids = self._copy_bullets(chain, power, result, attack_param, narrow_root, add_status=True)
        new_root = new_ids[chain[0]]
        if motion:
            self.store.set("Bullet", new_root, motion)

        if child is not None:
            last = new_ids[chain[-1]]
            if self.store.values("Bullet", last)["HitBulletID"] <= 0:  # chains that loop back keep their loop
                child_chain = bullet_chain(self.base, child[1])[:MAX_CHAIN]
                result.child_power = own_power * CHILD_POWER
                child_ids = self._copy_bullets(child_chain, result.child_power, result, attack_param, False)
                child_last = child_ids[child_chain[-1]]
                if self.store.values("Bullet", child_last)["HitBulletID"] not in child_ids.values():
                    self.store.set("Bullet", child_last, {"HitBulletID": -1})  # cut where the copy was truncated
                self.store.set("Bullet", last, {"HitBulletID": child_ids[child_chain[0]]})
            else:
                result.chained_from = None
                result.power = clamp(power / CHAINED_PARENT_POWER)

        if visual_pool and rng.random() < options.visual_chance:
            source = rng.choice(visual_pool)
            sfx = self.base.params["Bullet"].row_values(source[1])
            self.store.set("Bullet", new_root, {f: sfx[f] for f in ("sfxId_Bullet", "sfxId_Hit", "sfxId_Flick")})
            result.visual_from = source[0]
            if len(chain) > 1 and rng.random() < options.visual_chance / 2:
                impact = self.base.params["Bullet"].row_values(rng.choice(visual_pool)[1])
                self.store.set("Bullet", new_ids[rng.choice(chain[1:])],
                               {f: impact[f] for f in ("sfxId_Bullet", "sfxId_Hit")})
        return new_root

    def _motion(self, donor_root: int, root_class, options: ChainOptions, result) -> dict:
        """Speed / homing changes for moving root bullets; "_power" is the power factor they cost."""
        if root_class.motion not in ("linear", "homing", "lobbed") or self.rng.random() >= options.motion_chance:
            return {}
        values = self.base.params["Bullet"].row_values(donor_root)
        speed = self.rng.uniform(*SPEED_RANGE)
        updates = {f: values[f] * speed for f in SPEED_FIELDS if values[f]}
        cost = 1 - SPEED_POWER_COST * max(speed - 1, 0) + SPEED_POWER_COST * max(1 - speed, 0)
        if root_class.motion == "homing":
            updates["homingAngle"] = max(1, int(round(values["homingAngle"] * self.rng.uniform(*HOMING_RANGE))))
        elif root_class.motion == "linear" and "stream" not in root_class.qualifiers \
                and self.rng.random() < ADD_HOMING_CHANCE:
            updates["homingAngle"] = self.rng.randint(*ADDED_HOMING_ANGLE)
            cost *= ADDED_HOMING_POWER
        result.motion = f"speed x{speed:.2f}" + (f", homing {updates['homingAngle']}" if "homingAngle" in updates else "")
        updates["_power"] = cost
        return updates

    def _copy_bullets(self, chain: list[int], power: float, result, attack_param: str, narrow_root: bool,
                      add_status: bool = False) -> dict[int, int]:
        """Copy `chain` into new Bullet rows (relinked among themselves), with scaled attack and effect copies."""
        new_ids = {}
        for i, bullet in enumerate(chain):
            new_ids[bullet] = self.ids.allocate("Bullet", S16_MAX if narrow_root and i == 0 else 2**31 - 1)
            self.store.add("Bullet", new_ids[bullet], copy_from=bullet)
            result.rows["Bullet"] += 1

        status_added = not (add_status and result.status)
        damaging = [b for b in chain if self.base.params["Bullet"].row_values(b)["atkId_Bullet"] > 0]
        for bullet in chain:
            values = self.base.params["Bullet"].row_values(bullet)
            updates = {}
            if values["HitBulletID"] in new_ids:
                updates["HitBulletID"] = new_ids[values["HitBulletID"]]
            source = self._attack_source(bullet) if self._attack_source else attack_param
            if values["atkId_Bullet"] > 0 and values["atkId_Bullet"] in self.base.params[source].rows:
                updates["atkId_Bullet"] = self.copy_attack(attack_param, values["atkId_Bullet"], power, result,
                                                           source_param=source)
            for name in ["spEffectIDForShooter"] + [f"spEffectId{i}" for i in range(5)]:
                if values[name] > 0 and self.scalable(values[name]):
                    updates[name] = self.copy_speffect(values[name], power, result)
            if result.status and not status_added and damaging and bullet == damaging[-1]:
                free = next((f"spEffectId{i}" for i in range(5) if values[f"spEffectId{i}"] <= 0), None)
                if free:
                    updates[free] = result.status
                    status_added = True
            if updates:
                self.store.set("Bullet", new_ids[bullet], updates)
        if add_status and result.status and not status_added:
            result.status = None
        return new_ids

    def copy_attack(self, attack_param: str, attack: int, power: float, result, source_param: str | None = None) -> int:
        """Copy an attack (from `source_param`, default the same table) into `attack_param`, scaling its flat damage,
        or, for attacks without flat damage that scale the wielded weapon (arrows, bolts), its correction
        percentages. AtkParam_Pc and AtkParam_Npc share one row layout."""
        source_param = source_param or attack_param
        values = self.base.params[source_param].row_values(attack)
        new_id = self.ids.allocate(attack_param)
        if source_param == attack_param:
            self.store.add(attack_param, new_id, copy_from=attack)
        else:
            self.store.add(attack_param, new_id, copy_from=min(self.base.params[attack_param].rows))
            self.store.set(attack_param, new_id, values)
        fields = DAMAGE_FIELDS if any(values[f] for f in DAMAGE_FIELDS) else CORRECTION_FIELDS
        self.store.set(attack_param, new_id, {f: int(round(values[f] * power)) for f in fields if values[f]})
        result.rows[attack_param] += 1
        return new_id

    def scalable(self, speffect: int) -> bool:
        if speffect not in self.base.params["SpEffectParam"].rows:
            return False
        if speffect in self.store.protected.get("SpEffectParam", set()):
            return False
        effect = self.classifier.speffect(speffect)
        return effect.state is None and bool(set(effect.groups) & set(SCALED_GROUPS))

    def copy_speffect(self, speffect: int, power: float, result, root: bool = False) -> int:
        new_id = self.ids.allocate("SpEffectParam", S16_MAX if root else 2**31 - 1)
        self.store.add("SpEffectParam", new_id, copy_from=speffect)
        result.rows["SpEffectParam"] += 1
        values = self.base.params["SpEffectParam"].row_values(speffect)
        neutral = self.classifier.neutral
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


def chain_damage(session: Session, root: int, attack_param: str) -> int:
    """Total flat damage of a chain (sum of damage fields of each bullet's attack x shots)."""
    bullets, attacks = session.base.params["Bullet"], session.base.params[attack_param]
    total = 0
    for bullet in bullet_chain(session.base, root):
        values = bullets.row_values(bullet)
        if values["atkId_Bullet"] > 0 and values["atkId_Bullet"] in attacks.rows:
            atk = attacks.row_values(values["atkId_Bullet"])
            total += sum(atk[f] for f in DAMAGE_FIELDS) * max(values["numShoot"], 1)
    return total
