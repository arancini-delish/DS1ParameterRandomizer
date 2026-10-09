"""Subtype classification of Bullet and Magic rows (Phase 4b).

Rows with the same subtype are candidates for swapping verbatim. Classification uses vanilla field values; every row gets
exactly one subtype (rules are ordered), and rows that fall through to a catch-all are reported by `coverage`.

Bullet subtype = motion, plus qualifiers:
    orbit       funnel AI (`autoSearchNPCThinkID`), e.g. Homing Soulmass orbs
    attached    follows its owner (`FollowType`)
    ground      spawned at ground positions (`EmittePosType`): 2 ahead of the shooter, 1 around it
    stationary  no velocity: explosions, clouds, point-blank hits, spawners
    homing      moving with homing (`homingAngle`)
    lobbed      moving with gravity in range (arcs)
    linear      moving straight
  qualifiers (suffixes): lingering (lives >= 2 s and re-hits), instant (lives <= 0.1 s), multi (several per launch),
  stream (repeats at an interval)
  payload (separate, for compatibility checks): damage, target_effect, shooter_effect, spawns_child

Magic subtype = school / cast animation category (`refType`), e.g. "sorcery/projectile". The cast animation decides how
the spell is delivered (some animations spawn bullets continuously), so spells only swap within a category. Names of the
categories are read from which vanilla spells use them.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ds1rand.baseline.store import Baseline

# Magic `ezStateBehaviorType`. (Meta's MAGIC_CATEGORY labels are wrong for DS1: 0 is Soul Arrow, 1 Heal, 2 Fireball.)
SCHOOLS = {0: "sorcery", 1: "miracle", 2: "pyromancy"}

# Magic `refType` (cast animation category) -> name, from the vanilla spells using each.
CAST_ANIMATIONS = {
    0: "projectile",  # Soul Arrow, Homing Soulmass, Soul Spear, Aural Decoy, Dark Bead
    22: "projectile_charged",  # Heavy Soul Arrow, Dark Orb, Pursuers, White Dragon Breath
    19: "spear_throw",  # Lightning Spear family
    5: "thrown",  # Fireball family
    1: "weapon_buff",  # Magic Weapon family, Hidden Weapon
    15: "weapon_buff_blade",  # Sunlight / Darkmoon Blade
    17: "shield_buff",  # Magic Shield family
    2: "self_sorcery",  # Hidden Body, Hush, Repair, Fall Control, Remedy, Resist Curse
    20: "cast_light",
    13: "chameleon",
    3: "self_miracle",  # Heal family, Homeward, barriers, Karmic Justice, Tranquil Walk, Vow of Silence
    4: "area_heal",  # Soothing / Bountiful Sunlight
    6: "self_pyromancy",  # Iron Flesh, Flash Sweat, Power Within
    8: "point_blank",  # Combustion, Black Flame
    9: "mist",  # Poison / Toxic Mist, Acid Surge
    10: "ground_eruption",  # Firestorm, Fire Tempest, Chaos Storm
    11: "undead_rapport",
    12: "force",  # Force, Wrath of the Gods
    18: "emit_force",
    16: "ground_trace",  # Gravelord Sword Dances
    23: "spray",  # Fire Surge
    24: "whip",  # Fire Whip, Chaos Fire Whip
}


@dataclass(frozen=True)
class BulletClass:
    motion: str
    qualifiers: tuple[str, ...]
    payload: tuple[str, ...]

    @property
    def subtype(self) -> str:
        return "_".join((self.motion, *self.qualifiers))


def classify_bullet(v: dict) -> BulletClass:
    moving = v["initVellocity"] > 0 or v["maxVellocity"] > 0
    if v["autoSearchNPCThinkID"] > 0:
        motion = "orbit"
    elif v["FollowType"] != 0:
        motion = "attached"
    elif v["EmittePosType"] != 0:
        motion = "ground"
    elif not moving:
        motion = "stationary"
    elif v["homingAngle"] > 0:
        motion = "homing"
    elif v["gravityInRange"] > 0:
        motion = "lobbed"
    else:
        motion = "linear"

    qualifiers = []
    if v["life"] >= 2 and v["dmgHitRecordLifeTime"] > 0:
        qualifiers.append("lingering")
    elif 0 <= v["life"] <= 0.1:
        qualifiers.append("instant")
    if v["numShoot"] > 1:
        qualifiers.append("multi")
    if v["shootInterval"] > 0:
        qualifiers.append("stream")

    payload = []
    if v["atkId_Bullet"] > 0:
        payload.append("damage")
    if any(v[f"spEffectId{i}"] > 0 for i in range(5)):
        payload.append("target_effect")
    if v["spEffectIDForShooter"] > 0:
        payload.append("shooter_effect")
    if v["HitBulletID"] > 0:
        payload.append("spawns_child")
    return BulletClass(motion, tuple(qualifiers), tuple(payload))


def bullet_chain(baseline: Baseline, bullet_id: int) -> list[int]:
    """`bullet_id` and the bullets it spawns on hit, in order (stops at missing rows or cycles)."""
    rows = baseline.params["Bullet"]
    chain = []
    while bullet_id > 0 and bullet_id in rows.rows and bullet_id not in chain:
        chain.append(bullet_id)
        bullet_id = rows.row_values(bullet_id)["HitBulletID"]
    return chain


@dataclass(frozen=True)
class SpellClass:
    school: str
    cast: str
    delivery: str  # "bullet" or "speffect"
    root_bullet: BulletClass | None
    chain_length: int

    @property
    def subtype(self) -> str:
        return f"{self.school}/{self.cast}"


def classify_magic(baseline: Baseline, row_id: int) -> SpellClass:
    v = baseline.params["Magic"].row_values(row_id)
    school = SCHOOLS.get(v["ezStateBehaviorType"], f"school{v['ezStateBehaviorType']}")
    cast = CAST_ANIMATIONS.get(v["refType"], f"unknown{v['refType']}")
    if v["refCategory"] == 1:
        chain = bullet_chain(baseline, v["refId"])
        root = classify_bullet(baseline.params["Bullet"].row_values(chain[0])) if chain else None
        return SpellClass(school, cast, "bullet", root, len(chain))
    return SpellClass(school, cast, "speffect", None, 0)


def coverage(baseline: Baseline, rows: dict[str, list[int]]) -> dict[str, Counter]:
    """Subtype counts for the given Bullet and Magic rows; catch-all subtypes start with "unknown"."""
    result = {"Bullet": Counter(), "Magic": Counter()}
    for row_id in rows.get("Bullet", []):
        result["Bullet"][classify_bullet(baseline.params["Bullet"].row_values(row_id)).subtype] += 1
    for row_id in rows.get("Magic", []):
        result["Magic"][classify_magic(baseline, row_id).subtype] += 1
    return result
