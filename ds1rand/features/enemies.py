"""Enemy behaviour randomizer (Phase 6.4): how enemies turn, notice, chase, move, stagger and tire.

Each enemy type (an NpcParam row placed in a map) draws a tier from the distribution; each enabled group of fields then
gets one factor from that tier's range, so related fields move together (e.g. the three leash distances keep their
order). Higher factors make enemies harder.

    turn       NpcParam.turnVellocity (degrees per second; 0 = cannot turn and 9999 = instant are left alone)
    detection  NpcThinkParam sight / hearing / smell distances and sight / hearing angles
    pursuit    NpcThinkParam leash distances (how far an enemy follows before going home) and how long it remembers a
               target it lost sight / sound of
    poise      NpcParam.superArmorDurability (only enemies that have poise)
    stamina    NpcParam stamina and stamina recovery (how much blocking they can take)
    speed      movement: fast tiers walk with their run animation, slow tiers run with their walk animation. DS1 has no
               movement speed field: the MoveParam row an enemy uses lists its walk / run animations, so this copies
               that row with the forward walk and run swapped. Enemies without a run animation are unaffected.

Detection and pursuit live in NpcThinkParam rows, which the maps assign per placed enemy and which several enemy types
can share: a think row follows the enemy type that uses it most. Values stay within the vanilla extremes of each field
(sentinels like 9999 = unlimited are kept as they are), angles within their engine limits.

Categories: `regular` enemies, `boss` (characters events give a boss health bar, found from the installed event scripts
and maps, so this follows bosses the enemy randomizer moved) and `human` (c0000 or NpcParam rows below 100000: NPCs, invaders, phantoms). Only
enemy types placed in a map are randomized.
"""
from __future__ import annotations

import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import IntEnum

from ds1rand.defs.meta import load_row_names
from ds1rand.graph.model import Node
from ds1rand.session import Session


class BehaviourTier(IntEnum):
    SLUGGISH = 0
    NORMAL = 1
    ALERT = 2
    RELENTLESS = 3


TIER_RANGE = {
    BehaviourTier.SLUGGISH: (0.6, 0.85),
    BehaviourTier.NORMAL: (0.9, 1.1),
    BehaviourTier.ALERT: (1.15, 1.45),
    BehaviourTier.RELENTLESS: (1.45, 1.9),
}
PRESETS = {
    "Easy": (0.4, 0.45, 0.12, 0.03),
    "Standard": (0.15, 0.55, 0.22, 0.08),
    "Hard": (0.05, 0.4, 0.35, 0.2),
    "Misery": (0.0, 0.2, 0.4, 0.4),
}
CATEGORIES = ("regular", "boss", "human")
SPEED_UP, SLOW_DOWN = 1.25, 0.8  # speed factors at or beyond which walk / run animations are swapped

# group -> (param, fields); a field is (name, engine limit or None).
GROUPS: dict[str, tuple[str, tuple[tuple[str, float | None], ...]]] = {
    "turn": ("NpcParam", (("turnVellocity", None),)),
    "detection": ("NpcThinkParam", (("eye_dist", None), ("ear_dist", None), ("nose_dist", None), ("eye_angX", 180),
                                    ("eye_angY", 180), ("ear_angX", 90), ("ear_angY", 180))),
    "pursuit": ("NpcThinkParam", (("maxBackhomeDist", None), ("backhomeDist", None), ("backhomeBattleDist", None),
                                  ("SightTargetForgetTime", None), ("SoundTargetForgetTime", None))),
    "poise": ("NpcParam", (("superArmorDurability", None),)),
    "stamina": ("NpcParam", (("stamina", None), ("staminaRecoverBaseVel", None))),
}
SENTINEL = 9999  # "unlimited" / "instant" in distance, time and turn fields
HUMAN_MODEL = "c0000"
HUMAN_ROWS = 100000  # NpcParam rows below this are human characters (NPCs, invaders, phantoms)


@dataclass
class EnemyConfig:
    tier_weights: tuple[float, float, float, float] = PRESETS["Standard"]
    groups: dict[str, bool] = field(default_factory=lambda: dict.fromkeys((*GROUPS, "speed"), True))
    categories: dict[str, bool] = field(default_factory=lambda: {"regular": True, "boss": False, "human": False})


@dataclass
class EnemyResult:
    npc_id: int
    model: str
    category: str
    tier: BehaviourTier
    factors: dict[str, float] = field(default_factory=dict)
    think_rows: list[int] = field(default_factory=list)
    speed: str = ""  # "faster" / "slower" when the movement animations were swapped
    name: str = ""


@dataclass
class EnemyType:
    npc_id: int
    model: str
    category: str
    think_rows: Counter = field(default_factory=Counter)  # think row -> placements with this enemy type


def boss_entities(session: Session) -> set[int]:
    return {e.dst.id for e in session.graph.edges if e.dst.kind == "entity" and e.dst.name == "boss"}


def enemy_types(session: Session) -> dict[int, EnemyType]:
    """Placed enemy types (NpcParam rows referenced by map characters) with their model, category and think rows."""
    bosses = boss_entities(session)
    graph = session.graph
    npc_rows = session.base.params["NpcParam"].rows
    think_rows = session.base.params["NpcThinkParam"].rows
    types: dict[int, EnemyType] = {}
    boss_rows: set[int] = set()
    for npc_id in sorted(npc_rows):
        placements = [e.src for e in graph.users_of(Node.param("NpcParam", npc_id))
                      if e.src.kind == "msb" and e.field == "character_id"]
        if not placements:
            continue
        models, thinks = Counter(), Counter()
        for part in placements:
            if part.id in bosses:
                boss_rows.add(npc_id)
            for ref in graph.refs_of(part):
                if ref.field == "model":
                    models[ref.dst.name] += 1
                elif ref.field == "ai_id" and ref.dst.id in think_rows:
                    thinks[ref.dst.id] += 1
        model = models.most_common(1)[0][0] if models else f"c{npc_id // 100:04d}"
        human = model == HUMAN_MODEL or npc_id < HUMAN_ROWS  # the enemy randomizer re-skins some human rows
        category = "boss" if npc_id in boss_rows else "human" if human else "regular"
        types[npc_id] = EnemyType(npc_id, model, category, thinks)
    return types


def field_limits(session: Session, param: str, rows) -> dict[str, tuple[float, float]]:
    """Vanilla extremes of each grouped field over the given rows, ignoring 0 and sentinels."""
    values = session.vanilla.params[param] if param in session.vanilla.params else session.base.params[param]
    limits = {}
    for _group, (group_param, fields) in GROUPS.items():
        if group_param != param:
            continue
        for name, cap in fields:
            seen = [values.row_values(r)[name] for r in rows if r in values.rows]
            seen = [v for v in seen if 0 < v < SENTINEL]
            if seen:
                limits[name] = (min(seen), min(max(seen), cap) if cap else max(seen))
    return limits


def scaled(value, factor: float, limits: tuple[float, float] | None, is_int: bool):
    if value <= 0 or value >= SENTINEL or limits is None:
        return value
    low, high = limits
    new = min(max(value * factor, min(low, value)), max(high, value))
    return int(round(new)) if is_int else float(new)


class _EnemyBuilder:
    def __init__(self, session: Session, config: EnemyConfig, rng: random.Random):
        self.session = session
        self.config = config
        self.rng = rng
        self.types = enemy_types(session)
        self.limits = {
            "NpcParam": field_limits(session, "NpcParam", self.types),
            "NpcThinkParam": field_limits(session, "NpcThinkParam",
                                          {t for e in self.types.values() for t in e.think_rows}),
        }
        self.move_copies: dict[tuple[int, str], int] = {}
        usage = session.usage
        # Think rows also used outside enemies (e.g. homing bullets' target search) stay as they are.
        self.enemy_only_thinks = {
            t for e in self.types.values() for t in e.think_rows
            if usage.get(Node.param("NpcThinkParam", t), set()) == {"enemy"}
        }

    def enabled(self, enemy: EnemyType) -> bool:
        return self.config.categories.get(enemy.category, False)

    def draw(self, enemy: EnemyType) -> EnemyResult:
        tier = BehaviourTier(self.rng.choices(range(len(BehaviourTier)), weights=self.config.tier_weights)[0])
        low, high = TIER_RANGE[tier]
        result = EnemyResult(enemy.npc_id, enemy.model, enemy.category, tier)
        for group in (*GROUPS, "speed"):
            if self.config.groups.get(group, False):
                result.factors[group] = round(self.rng.uniform(low, high), 3)
        return result

    def apply_npc(self, result: EnemyResult) -> None:
        npc = self.session.base.params["NpcParam"].row_values(result.npc_id)
        updates = {}
        for group, (param, fields) in GROUPS.items():
            if param != "NpcParam" or group not in result.factors:
                continue
            for name, _cap in fields:
                new = scaled(npc[name], result.factors[group], self.limits["NpcParam"].get(name),
                             isinstance(npc[name], int))
                if new != npc[name]:
                    updates[name] = new
        if "speed" in result.factors:
            move = self._speed(npc["moveAnimId"], result.factors["speed"])
            if move is not None:
                updates["moveAnimId"], result.speed = move
        if updates:
            self.session.store.set("NpcParam", result.npc_id, updates)

    def _speed(self, move_id: int, factor: float) -> tuple[int, str] | None:
        moves = self.session.base.params["MoveParam"]
        if move_id not in moves.rows:
            return None
        row = moves.row_values(move_id)
        if row["dashF"] in (-1, row["walkF"]) or row["walkF"] == -1:
            return None
        if factor >= SPEED_UP:
            mode, updates = "faster", {"walkF": row["dashF"]}
        elif factor <= SLOW_DOWN:
            mode, updates = "slower", {"dashF": row["walkF"]}
        else:
            return None
        if (move_id, mode) not in self.move_copies:
            new_id = self.session.ids.allocate("MoveParam")
            self.session.store.add("MoveParam", new_id, copy_from=move_id)
            self.session.store.set("MoveParam", new_id, updates)
            self.move_copies[(move_id, mode)] = new_id
        return self.move_copies[(move_id, mode)], mode

    def apply_think(self, think_id: int, factors: dict[str, float]) -> None:
        think = self.session.base.params["NpcThinkParam"].row_values(think_id)
        updates = {}
        for group, (param, fields) in GROUPS.items():
            if param != "NpcThinkParam" or group not in factors:
                continue
            for name, _cap in fields:
                new = scaled(think[name], factors[group], self.limits["NpcThinkParam"].get(name), True)
                if new != think[name]:
                    updates[name] = new
        # Leash distances keep their vanilla order (battle <= home <= max) where they had it.
        if "pursuit" in factors:
            for small, large in (("backhomeBattleDist", "backhomeDist"), ("backhomeDist", "maxBackhomeDist")):
                values = {**think, **updates}
                if think[small] <= think[large] < SENTINEL and values[small] > values[large]:
                    updates[small] = values[large]
        if updates:
            self.session.store.set("NpcThinkParam", think_id, updates)


def randomize_enemies(session: Session, config: EnemyConfig, rng: random.Random) -> list[EnemyResult]:
    builder = _EnemyBuilder(session, config, rng)
    names = _names(session)
    results: dict[int, EnemyResult] = {}
    for npc_id, enemy in builder.types.items():
        if not builder.enabled(enemy):
            continue
        result = builder.draw(enemy)
        result.name = names.get(npc_id, "")
        builder.apply_npc(result)
        results[npc_id] = result

    # Each think row follows the enemy type placed with it most; rows shared with a type left alone (e.g. a boss
    # with bosses off) stay vanilla.
    think_users: dict[int, Counter] = defaultdict(Counter)
    for enemy in builder.types.values():
        for think_id, count in enemy.think_rows.items():
            think_users[think_id][enemy.npc_id] += count
    for think_id in sorted(builder.enemy_only_thinks):
        users = think_users[think_id]
        if any(npc_id not in results for npc_id in users):
            continue
        owner = max(users, key=lambda npc_id: (users[npc_id], -npc_id))
        builder.apply_think(think_id, results[owner].factors)
        results[owner].think_rows.append(think_id)
    return list(results.values())


def _names(session: Session) -> dict[int, str]:
    npc = session.base.params["NpcParam"]
    text = session.base.text.get(18, ("", {}))[1]  # NPC_name
    community = load_row_names("NpcParam")
    names = {}
    for npc_id in npc.rows:
        name_id = npc.row_values(npc_id)["nameId"]
        names[npc_id] = text.get(name_id) or community.get(npc_id) or community.get(npc_id - npc_id % 100, "")
    return names
