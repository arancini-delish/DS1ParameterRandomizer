"""Projectile randomizer (Phase 6.3): every non-spell bullet a player, enemy or trap fires.

A *slot* is a param field that fires a bullet chain:
    arrow / great_arrow / bolt   the ammo's behavior row (BehaviorParam_PC.refId; one per arrow, two per bolt).
                                 Great arrows (Dragonslayer, Gough's) are their own kind. NPC archers share these
                                 behaviors (engine-computed IDs), so they fire the randomized ammo too. Behaviors
                                 firing the same ammo bullet share one randomization.
    throwable                    EquipParamGoods.refId of the attack throwables (`THROWABLES`); utility goods that
                                 fire bullets (moss, Divine Blessing, Alluring Skull, Prism Stone...) are left alone
    enemy                        BehaviorParam.refId of NPC behaviors that fire bullets, grouped by character model
    trap                         BehaviorParam.refId of behaviors only events fire (traps, hazards)

Each slot gets a donor chain, copied into new rows (`chains.ChainBuilder`) with the shared visual, motion,
chained-effect and status options. Player donors keep their nature: arrows stay arrows (bow animations and ammo
association), throwables stay throwables.

Enemy and trap slots (`cross_enemy`, default) draw donors, visuals and chained effects from every projectile (enemy,
trap, player, and spells with `enemy_spells`) whose particle effects are loaded wherever the slot's projectile can
appear (`catalogue.ffx`: the always-loaded bundles plus the bundles of the maps the enemy model is placed in / the map
whose events fire the trap). Effects that are not loaded would make the projectile invisible. Donors share the slot's
motion (straight / homing / lobbed / stationary...); bullets bound to their owner's body (orbiting, attached) keep
same-model donors. With `cross_enemy` off, every enemy slot only draws on its own model's projectiles.

Power:
    player     a tier from the player distribution; ammo scales its attack corrections (arrows and bolts scale the
               bow's attack rating), throwables their damage, and throwables carry fewer per tier (`CARRY_LIMITS`)
    enemy/trap the slot's own vanilla damage x tier (from the enemy / environment distribution): a donor is rescaled
               to the damage of the projectile it replaces, so difficulty stays near the base game's
Player visuals and chained effects stay non-spell by default; `spell_effects` adds the spell pools (always loaded).
"""
from __future__ import annotations

import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import IntEnum

from ds1rand.catalogue.budget import reference_limits
from ds1rand.catalogue.ffx import bullet_effects
from ds1rand.catalogue.subtypes import bullet_chain, classify_bullet
from ds1rand.features.chains import (
    ChainBuilder, ChainOptions, chain_candidates, chain_damage, visual_candidates,
)
from ds1rand.graph.model import Node
from ds1rand.session import Session


class ProjectileTier(IntEnum):
    WEAK = 0
    STANDARD = 1
    STRONG = 2
    LEGENDARY = 3


TIER_POWER = {ProjectileTier.WEAK: 0.8, ProjectileTier.STANDARD: 1.0, ProjectileTier.STRONG: 1.25,
              ProjectileTier.LEGENDARY: 1.5}
CARRY_LIMITS = {ProjectileTier.WEAK: 99, ProjectileTier.STANDARD: 99, ProjectileTier.STRONG: 40,
                ProjectileTier.LEGENDARY: 20}
PRESETS = {
    "Easy": (0.15, 0.45, 0.3, 0.1),
    "Standard": (0.25, 0.5, 0.2, 0.05),
    "Hard": (0.4, 0.45, 0.12, 0.03),
    "Misery": (0.55, 0.38, 0.06, 0.01),
}
# Enemy / trap tiers: stronger enemy projectiles make the game harder, so the presets run the other way round.
ENEMY_PRESETS = {
    "Easy": (0.4, 0.45, 0.12, 0.03),
    "Standard": (0.2, 0.55, 0.2, 0.05),
    "Hard": (0.1, 0.45, 0.33, 0.12),
    "Misery": (0.05, 0.3, 0.4, 0.25),
}
POWER_LIMITS = (0.25, 4.0)
# Bullets that follow or circle their owner's body parts (dummy polys): only bullets of the same model fit them.
MODEL_BOUND_MOTIONS = ("orbit", "attached")

THROWABLES = frozenset({290, 291, 292, 293, 297})  # Throwing Knife, Poison Throwing Knife, Firebomb, Dung Pie,
                                                     # Black Firebomb
ARROW_VARIATIONS = range(1000, 1007)
GREAT_ARROW_VARIATIONS = range(1007, 1009)
BOLT_VARIATIONS = range(1100, 1105)


@dataclass(frozen=True, order=True)
class Slot:
    kind: str  # arrow, great_arrow, bolt, throwable, enemy, trap
    param: str
    row: int
    root: int  # vanilla root bullet
    group: str = ""  # donor/visual group: character model for enemies, the kind otherwise

    @property
    def owner(self) -> str:
        return {"enemy": "enemy", "trap": "environment"}.get(self.kind, "player")

    @property
    def attack_param(self) -> str:
        return "AtkParam_Pc" if self.owner == "player" else "AtkParam_Npc"


@dataclass
class ProjectileConfig:
    player_weights: tuple[float, float, float, float] = PRESETS["Standard"]
    enemy_weights: tuple[float, float, float, float] = ENEMY_PRESETS["Standard"]
    environment_weights: tuple[float, float, float, float] = ENEMY_PRESETS["Standard"]
    player: bool = True
    enemy: bool = True
    environment: bool = True
    visual_chance: float = 0.5
    motion_chance: float = 0.4
    chain_chance: float = 0.25
    status_chance: float = 0.15
    cross_enemy: bool = True
    spell_effects: bool = False
    enemy_spells: bool = True
    write_summaries: bool = True


@dataclass
class ProjectileResult:
    slot: Slot
    tier: ProjectileTier
    donor: int  # donor root bullet
    power: float = 1.0
    root: int = 0
    carry: int | None = None
    visual_from: int | None = None
    motion: str = ""
    chained_from: tuple[int, int] | None = None
    child_power: float = 0.0
    status: int | None = None
    rows: Counter = field(default_factory=Counter)


def find_slots(session: Session) -> list[Slot]:
    base = session.base
    usage = session.usage
    slots = []
    behaviors_pc = base.params["BehaviorParam_PC"]
    bullets = base.params["Bullet"].rows
    for row_id in sorted(behaviors_pc.rows):
        values = behaviors_pc.row_values(row_id)
        variation = values["variationId"]
        if values["refType"] != 1 or values["refId"] not in bullets:
            continue
        kind = ("arrow" if variation in ARROW_VARIATIONS else "great_arrow" if variation in GREAT_ARROW_VARIATIONS
                else "bolt" if variation in BOLT_VARIATIONS else None)
        if kind:
            slots.append(Slot(kind, "BehaviorParam_PC", row_id, values["refId"], kind))

    goods = base.params["EquipParamGoods"]
    for row_id in sorted(THROWABLES & set(goods.rows)):
        values = goods.row_values(row_id)
        if values["refCategory"] == 1 and values["refId"] in bullets:
            slots.append(Slot("throwable", "EquipParamGoods", row_id, values["refId"], "throwable"))

    behaviors = base.params["BehaviorParam"]
    for row_id in sorted(behaviors.rows):
        values = behaviors.row_values(row_id)
        if not row_id or values["refType"] != 1 or values["refId"] not in bullets:
            continue
        features = usage.get(Node.param("BehaviorParam", row_id), set())
        if "enemy" in features:
            models = sorted({e.src.name for e in session.graph.users_of(Node.param("BehaviorParam", row_id))
                             if e.src.kind == "tae"})
            # Behaviors no animation invokes have no known model: they only draw on themselves.
            slots.append(Slot("enemy", "BehaviorParam", row_id, values["refId"],
                              models[0] if models else f"unknown:{row_id}"))
        elif "environment" in features:
            slots.append(Slot("trap", "BehaviorParam", row_id, values["refId"], "trap"))
    return slots


class _ProjectileBuilder:
    def __init__(self, session: Session, config: ProjectileConfig, rng: random.Random):
        self.session = session
        self.config = config
        self.rng = rng
        self.chains = ChainBuilder(session, rng)
        self.slots = find_slots(session)
        self.limits = reference_limits(session.base)["Bullet"]
        self.options = ChainOptions(config.visual_chance, config.motion_chance, config.chain_chance,
                                    config.status_chance)
        self.bullets = session.base.params["Bullet"]

        self.by_group: dict[str, list[Slot]] = defaultdict(list)
        for slot in self.slots:
            self.by_group[slot.group].append(slot)
        self.pairs = {group: [(s.root, b) for s in slots for b in bullet_chain(session.base, s.root)]
                      for group, slots in self.by_group.items()}
        player_pairs = [p for kind in ("arrow", "great_arrow", "bolt", "throwable") for p in self.pairs.get(kind, [])]
        self.player_visuals = visual_candidates(session, player_pairs)
        self.player_chains = chain_candidates(session, player_pairs)
        spell_pairs = self._spell_pairs()
        self.spell_visuals, self.spell_chains = [], []
        if config.spell_effects:
            self.spell_visuals = visual_candidates(session, spell_pairs)
            self.spell_chains = chain_candidates(session, spell_pairs)

        # Which attack table each known bullet's attack ID refers to (who fires it).
        self.attack_table: dict[int, str] = {}
        for slot in self.slots:
            for bullet in bullet_chain(session.base, slot.root):
                self.attack_table.setdefault(bullet, slot.attack_param)
        for _root, bullet in spell_pairs:
            self.attack_table.setdefault(bullet, "AtkParam_Pc")

        # Enemy / trap pools: every projectile (and spell, with `enemy_spells`), filtered per slot by what is loaded.
        any_pairs = [p for pairs in self.pairs.values() for p in pairs] + (spell_pairs if config.enemy_spells else [])
        self.any_roots = sorted({root for root, _ in any_pairs})
        self.any_visuals = visual_candidates(session, any_pairs)
        self.any_chains = chain_candidates(session, any_pairs)
        self._loaded: dict[tuple, frozenset[int]] = {}

    def _spell_pairs(self) -> list[tuple[int, int]]:
        magic = self.session.base.params["Magic"]
        pairs = []
        for node in self.session.footprint("player_spell", {"Magic"}):
            values = magic.row_values(node.id)
            if values["refCategory"] == 1 and values["refId"] in self.bullets.rows:
                pairs += [(values["refId"], b) for b in bullet_chain(self.session.base, values["refId"])]
        return pairs

    def motion(self, root: int) -> str:
        return classify_bullet(self.bullets.row_values(root)).motion

    def effects(self, root: int) -> set[int]:
        """Particle effects the whole chain at `root` shows."""
        return set().union(*(bullet_effects(self.bullets.row_values(b)) for b in bullet_chain(self.session.base, root)))

    def loaded(self, slot: Slot) -> frozenset[int]:
        """Effects loaded wherever the slot's projectile can appear: the maps its enemy model is placed in, or the map
        whose events fire the trap; player projectiles (and anything else) get the always-loaded effects."""
        key = (slot.kind, slot.group if slot.kind == "enemy" else slot.row)
        if key not in self._loaded:
            graph, maps, models = self.session.graph, set(), ()
            if slot.kind == "enemy" and not slot.group.startswith("unknown"):
                maps = {e.src.name.split("/")[0] for e in graph.users_of(Node("model", slot.group, 0))
                        if e.src.kind == "msb"}
                models = (slot.group,)
            elif slot.kind == "trap":
                stems = {e.src.name for e in graph.users_of(Node.param(slot.param, slot.row)) if e.src.kind == "emevd"}
                maps = set() if "common" in stems else stems
            self._loaded[key] = self.session.effects.loaded(maps, models)
        return self._loaded[key]

    def cross(self, slot: Slot) -> bool:
        """Whether the slot draws on every projectile (residency permitting) rather than its own model's."""
        return (slot.owner != "player" and self.config.cross_enemy
                and self.motion(slot.root) not in MODEL_BOUND_MOTIONS)

    def donors(self, slot: Slot) -> list[int]:
        if self.cross(slot):
            motion, loaded = self.motion(slot.root), self.loaded(slot)
            same = [r for r in self.any_roots if self.motion(r) == motion and self.effects(r) <= loaded]
            return same or [slot.root]
        return [s.root for s in self.by_group[slot.group]] or [slot.root]

    def pools(self, slot: Slot) -> tuple[list, list]:
        if slot.owner == "player":
            return self.player_visuals + self.spell_visuals, self.player_chains + self.spell_chains
        if self.cross(slot):
            loaded = self.loaded(slot)
            visuals = [p for p in self.any_visuals if bullet_effects(self.bullets.row_values(p[1])) <= loaded]
            chains = [p for p in self.any_chains if self.effects(p[1]) <= loaded]
            return visuals, chains
        group_pairs = self.pairs.get(slot.group, [])
        return visual_candidates(self.session, group_pairs), chain_candidates(self.session, group_pairs)

    def weights(self, slot: Slot):
        return {"player": self.config.player_weights, "enemy": self.config.enemy_weights,
                "environment": self.config.environment_weights}[slot.owner]

    def build(self, slot: Slot) -> ProjectileResult:
        rng = self.rng
        tier = ProjectileTier(rng.choices(range(len(ProjectileTier)), weights=self.weights(slot))[0])
        donor = rng.choice(self.donors(slot))
        source = lambda bullet: self.attack_table.get(bullet, slot.attack_param)  # noqa: E731
        # Enemy and trap donors are rescaled to the damage of the projectile they replace; the power limits
        # bound the tier (and motion / chain costs) around that, not the rescaling itself.
        scale = 1.0
        if slot.owner != "player":
            own = chain_damage(self.session, slot.root, slot.attack_param)
            theirs = chain_damage(self.session, donor, source(donor))
            if own and theirs:
                scale = own / theirs
        power = TIER_POWER[tier] * scale
        limits = (POWER_LIMITS[0] * scale, POWER_LIMITS[1] * scale)
        result = ProjectileResult(slot, tier, donor)
        visuals, chains = self.pools(slot)
        narrow = self.limits.get((slot.param, "refId"), 2**31 - 1) <= 32767
        result.root = self.chains.build(
            donor, power, result, attack_param=slot.attack_param, options=self.options, visual_pool=visuals,
            chain_pool=chains, narrow_root=narrow, limits=limits, attack_source=source,
        )
        updates = {"refId": result.root}
        if slot.kind == "throwable":
            result.carry = CARRY_LIMITS[tier]
            self.session.store.set("EquipParamGoods", slot.row, {"maxNum": result.carry})
        self.session.store.set(slot.param, slot.row, updates)
        return result


def summary(result: ProjectileResult) -> str:
    parts = [result.tier.name.title()]
    if result.carry is not None:
        parts.append(f"carry {result.carry}")
    if result.status:
        parts.append("inflicts status")
    if result.chained_from:
        parts.append("chained effect")
    return " - ".join(parts)


def randomize_projectiles(session: Session, config: ProjectileConfig, rng: random.Random) -> list[ProjectileResult]:
    builder = _ProjectileBuilder(session, config, rng)
    enabled = {"player": config.player, "enemy": config.enemy, "environment": config.environment}
    results = []
    ammo: dict[tuple[str, int], ProjectileResult] = {}
    for slot in builder.slots:
        if not enabled[slot.owner]:
            continue
        shared = ammo.get((slot.kind, slot.root)) if slot.param == "BehaviorParam_PC" else None
        if shared is not None:
            # A bolt's behaviors fire the same bullet: they share one randomization.
            session.store.set(slot.param, slot.row, {"refId": shared.root})
            continue
        result = builder.build(slot)
        if slot.param == "BehaviorParam_PC":
            ammo[(slot.kind, slot.root)] = result
        if slot.kind == "throwable" and config.write_summaries:
            session.text[("Item_description", slot.row)] = summary(result)
        results.append(result)
    return results
