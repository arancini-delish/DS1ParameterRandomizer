"""SpEffect and AtkParam classification (Phase 4b part 2).

SpEffect subtype = context / kind:
    context  how the row is reached (first in `CONTEXT_ORDER` when several apply): ring, armor, weapon, spell,
             consumable, shooter (bullet's effect on its shooter), on_hit (bullet/attack target effects), npc (innate
             NpcParam effects), animation, chained (another SpEffect's expire/cycle/attack effect), ai, event, engine,
             other; "unused" when nothing references it.
    kind     what it does, from which field groups differ from their vanilla neutral value (the most common value of
             the field across all rows; paramdef defaults are often wrong for DS1): session (multiplayer requests),
             else the first payload group in `GROUP_ORDER`, else state:<SP_EFFECT_TYPE name> (`stateInfo` only:
             engine-implemented behaviour), else trigger (only chains to other effects), visual (only a particle),
             marker (nothing: a flag that scripts and AI test for).
`groups` lists every payload group and `state` the `stateInfo` name (None if neutral); swaps must keep the state, since
the engine implements it.

AtkParam subtype = delivery / element: delivery from what references it (behavior hitbox, bullet impact, throw,
other, unused), element the largest of physical / magic / fire / lightning flat damage; "weapon_scaled" for player
attacks with no flat damage (they scale the wielded weapon's attack through `atk*Correction`), "none" for other
zero-damage hits; "+status" when the hit applies SpEffects.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import cached_property

from ds1rand.baseline.store import Baseline
from ds1rand.defs.meta import load_shared_enums
from ds1rand.graph.model import Node, RefGraph

GROUP_FIELDS = {
    "status": ("poizonAttackPower", "registIllness", "registBlood", "registCurse", "registPoizonChangeRate",
               "registIllnessChangeRate", "registBloodChangeRate", "registCurseChangeRate", "disablePoison",
               "disableDisease", "disableBlood", "disableCurse", "bloodDamageRate"),
    "regen": ("changeHpRate", "changeHpPoint", "changeMpRate", "changeMpPoint", "changeStaminaRate",
              "staminaRecoverChangeSpeed", "hpRecoverRate"),
    "attack": ("physicsAttackRate", "magicAttackRate", "fireAttackRate", "thunderAttackRate", "physicsAttackPowerRate",
               "magicAttackPowerRate", "fireAttackPowerRate", "thunderAttackPowerRate", "physicsAttackPower",
               "magicAttackPower", "fireAttackPower", "thunderAttackPower", "staminaAttackRate", "bowDistRate"),
    "defense": ("slashDamageCutRate", "blowDamageCutRate", "thrustDamageCutRate", "neutralDamageCutRate",
                "magicDamageCutRate", "fireDamageCutRate", "thunderDamageCutRate", "physicsDiffenceRate",
                "magicDiffenceRate", "fireDiffenceRate", "thunderDiffenceRate", "physicsDiffence", "magicDiffence",
                "fireDiffence", "thunderDiffence", "guardStaminaCutRate", "defFlickPower", "changeSuperArmorPoint",
                "NoGuardDamageRate"),
    "max_stats": ("maxHpRate", "maxMpRate", "maxStaminaRate", "changeMagicSlot", "changeMiracleSlot"),
    "enchant": ("atkAttribute", "spAttribute", "wepParamChange"),
    "souls": ("soul", "soulRate", "haveSoulRate", "soulStealRate", "clearSoul", "heroPointDamage"),
    "stealth": ("sightSearchEnemyCut", "hearingSearchEnemyCut", "targetPriority", "sightSearchCutIgnore",
                "hearingSearchCutIgnore", "fakeTargetIgnore", "fakeTargetIgnoreUndead", "antiMagicIgnore"),
    "durability": ("insideDurability", "maxDurability", "corrosionIgnore"),
    "movement": ("grabityRate", "grabityIgnore", "moveType", "fallDamageRate", "equipWeightChangeRate",
                 "allItemWeightChangeRate", "animIdOffset"),
    "stagger": ("dmgLv_None", "dmgLv_S", "dmgLv_M", "dmgLv_L", "dmgLv_BlowM", "dmgLv_Push", "dmgLv_Strike",
                "dmgLv_BlowS", "dmgLv_Min", "dmgLv_Uppercut", "dmgLv_BlowLL", "dmgLv_Breath"),
    "charm": ("enableCharm",),
}
GROUP_ORDER = tuple(GROUP_FIELDS)
SESSION_FIELDS = ("requestSOS", "requestBlackSOS", "requestForceJoinBlackSOS", "requestKickSession",
                  "requestLeaveSession", "requestNpcInveda", "requestLeaveColiseumSession")
TRIGGER_FIELDS = ("replaceSpEffectId", "cycleOccurrenceSpEffectId", "atkOccurrenceSpEffectId")
VISUAL_FIELDS = ("useSpEffectEffect",)

CONTEXT_ORDER = ("ring", "armor", "weapon", "spell", "consumable", "shooter", "on_hit", "npc", "animation", "chained",
                 "ai", "event", "engine", "other")


def _speffect_context(src: Node, field: str) -> str:
    if src.kind == "tae":
        return "animation"
    if src.kind == "lua":
        return "ai"
    if src.kind in ("emevd", "msb"):
        return "event"
    if src.kind == "engine":
        return "engine"
    return {
        "EquipParamAccessory": "ring",
        "EquipParamProtector": "armor",
        "EquipParamWeapon": "weapon",
        "ReinforceParamWeapon": "weapon",
        "ReinforceParamProtector": "armor",
        "Magic": "spell",
        "EquipParamGoods": "consumable",
        "NpcParam": "npc",
        "SpEffectParam": "chained",
        "AtkParam_Pc": "on_hit",
        "AtkParam_Npc": "on_hit",
        "BehaviorParam": "on_hit",
        "BehaviorParam_PC": "on_hit",
    }.get(src.name, "shooter" if field == "spEffectIDForShooter" else "on_hit" if src.name == "Bullet" else "other")


@dataclass(frozen=True)
class EffectClass:
    contexts: tuple[str, ...]
    kind: str
    groups: tuple[str, ...]
    state: str | None

    @property
    def subtype(self) -> str:
        return f"{self.contexts[0] if self.contexts else 'unused'}/{self.kind}"


class EffectClassifier:
    def __init__(self, baseline: Baseline, graph: RefGraph):
        self.baseline = baseline
        self.graph = graph
        self.states = load_shared_enums()["SP_EFFECT_TYPE"]

    @cached_property
    def neutral(self) -> dict[str, object]:
        """Most common vanilla value of each SpEffect field."""
        pb = self.baseline.params["SpEffectParam"]
        return {f: Counter(values[i] for values in pb.rows.values()).most_common(1)[0][0] for i, f in enumerate(pb.fields)}

    def speffect(self, row_id: int) -> EffectClass:
        v = self.baseline.params["SpEffectParam"].row_values(row_id)
        changed = {f for f, value in v.items() if value != self.neutral[f]}
        contexts = {_speffect_context(e.src, e.field) for e in self.graph.users_of(Node.param("SpEffectParam", row_id))}
        ordered = tuple(c for c in CONTEXT_ORDER if c in contexts)
        groups = tuple(g for g in GROUP_ORDER if changed & set(GROUP_FIELDS[g]))
        state = None
        if v["stateInfo"] != self.neutral["stateInfo"]:
            state = str(self.states.get(v["stateInfo"], v["stateInfo"]))
        if changed & set(SESSION_FIELDS):
            kind = "session"
        elif groups:
            kind = groups[0]
        elif state is not None:
            kind = f"state:{state}"
        elif changed & set(TRIGGER_FIELDS):
            kind = "trigger"
        elif changed & set(VISUAL_FIELDS):
            kind = "visual"
        else:
            kind = "marker"
        return EffectClass(ordered, kind, groups, state)

    def attack(self, param: str, row_id: int) -> str:
        v = self.baseline.params[param].row_values(row_id)
        users = self.graph.users_of(Node.param(param, row_id))
        sources = {e.src.name if e.src.kind == "param" else e.src.kind for e in users}
        if sources & {"BehaviorParam", "BehaviorParam_PC"}:
            delivery = "behavior"
        elif "Bullet" in sources:
            delivery = "bullet"
        elif "ThrowParam" in sources:
            delivery = "throw"
        elif sources:
            delivery = "other"
        else:
            delivery = "unused"
        damage = {"physical": v["atkPhys"], "magic": v["atkMag"], "fire": v["atkFire"], "lightning": v["atkThun"]}
        if max(damage.values()) > 0:
            element = max(damage, key=damage.get)
        elif param == "AtkParam_Pc" and any(v[f] > 0 for f in ("atkPhysCorrection", "atkMagCorrection",
                                                               "atkFireCorrection", "atkThunCorrection")):
            element = "weapon_scaled"
        else:
            element = "none"
        status = "+status" if any(v[f"spEffectId{i}"] > 0 for i in range(5)) else ""
        return f"{delivery}/{element}{status}"
