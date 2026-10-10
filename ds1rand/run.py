"""Running ds1rand from a preset: shared by the command line tool and the UI."""
from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ds1rand.features.appearance import AppearanceConfig, AppearanceResult, randomize_appearance
from ds1rand.features.armor import ArmorConfig, ArmorResult, randomize_armor
from ds1rand.features.enemies import GROUPS, EnemyConfig, EnemyResult, randomize_enemies
from ds1rand.features.rings import RingConfig, RingResult, randomize_rings
from ds1rand.features.projectiles import ProjectileConfig, ProjectileResult, randomize_projectiles
from ds1rand.features.spells import SpellConfig, SpellResult, randomize_spells
from ds1rand.features.weapons import WeaponConfig, WeaponResult, randomize_weapons
from ds1rand.io.install import GameInstall
from ds1rand.presets.schema import Preset
from ds1rand.session import Session

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "out" / "randomized"


@dataclass
class RunResult:
    seed: int
    gameparam_base: str
    text_base: str
    conflicts: list[str]
    foreign: list[str]
    rings: list[RingResult] = field(default_factory=list)
    ring_names: dict[int, str] = field(default_factory=dict)
    spells: list[SpellResult] = field(default_factory=list)
    spell_names: dict[int, str] = field(default_factory=dict)
    projectiles: list[ProjectileResult] = field(default_factory=list)
    goods_names: dict[int, str] = field(default_factory=dict)
    enemies: list[EnemyResult] = field(default_factory=list)
    weapons: list[WeaponResult] = field(default_factory=list)
    weapon_names: dict[int, str] = field(default_factory=dict)
    armor: list[ArmorResult] = field(default_factory=list)
    armor_names: dict[int, str] = field(default_factory=dict)
    appearance: AppearanceResult | None = None
    written: list[str] = field(default_factory=list)
    target: Path | None = None


def validate(install: GameInstall) -> RunResult:
    """Open a session without changing anything: which base would be used, what other mods changed."""
    session = Session.open(install)
    return _result(session, seed=0)


def run(
    preset: Preset,
    install: GameInstall,
    out_dir: Path | None = DEFAULT_OUT,
    log: Callable[[str], None] = print,
) -> RunResult:
    """Randomize with `preset` and write to `out_dir` (mirroring the game folder), or into the game folder if None."""
    seed = preset.seed if preset.seed is not None else random.randrange(2**31)
    log(f"Opening {install.root} ...")
    session = Session.open(install)
    result = _result(session, seed)
    log(f"Seed {seed}. GameParam base: {result.gameparam_base}; item text base: {result.text_base}")
    for conflict in result.conflicts:
        log(f"  conflict: {conflict}")
    for change in result.foreign:
        log(f"  kept from other mods: {change}")

    # One random stream per feature, so turning one feature on or off does not change another's results.
    if preset.rings.enabled:
        settings = preset.rings
        config = RingConfig(tier_weights=tuple(settings.tier_weights), isolate_npcs=settings.isolate_npcs,
                            write_summaries=settings.write_summaries)
        result.rings = randomize_rings(session, config, random.Random(f"{seed}-rings"))
        log(f"Rings: {len(result.rings)} randomized")
    if preset.spells.enabled:
        settings = preset.spells
        config = SpellConfig(tier_weights=tuple(settings.tier_weights), player=settings.player, enemy=settings.enemy,
                             visual_chance=settings.visual_chance, cross_school_visuals=settings.cross_school_visuals,
                             status_chance=settings.status_chance, write_summaries=settings.write_summaries,
                             motion_chance=settings.motion_chance, chain_chance=settings.chain_chance)
        result.spells = randomize_spells(session, config, random.Random(f"{seed}-spells"))
        log(f"Spells: {len(result.spells)} randomized "
            f"({sum(r.owner == 'player' for r in result.spells)} player, {sum(r.owner == 'enemy' for r in result.spells)} NPC)")

    if preset.projectiles.enabled:
        settings = preset.projectiles
        config = ProjectileConfig(**{f: getattr(settings, f) for f in (
            "player_weights", "enemy_weights", "environment_weights", "player", "enemy", "environment",
            "visual_chance", "motion_chance", "chain_chance", "status_chance", "cross_enemy", "spell_effects",
            "write_summaries", "enemy_spells")})
        result.projectiles = randomize_projectiles(session, config, random.Random(f"{seed}-projectiles"))
        kinds = Counter(r.slot.owner for r in result.projectiles)
        log(f"Projectiles: {len(result.projectiles)} randomized ({kinds['player']} player, {kinds['enemy']} enemy, "
            f"{kinds['environment']} traps)")

    if preset.enemies.enabled:
        settings = preset.enemies
        config = EnemyConfig(
            tier_weights=tuple(settings.tier_weights),
            groups={group: getattr(settings, group) for group in (*GROUPS, "speed")},
            categories={"regular": settings.regular, "boss": settings.bosses, "human": settings.humans},
        )
        result.enemies = randomize_enemies(session, config, random.Random(f"{seed}-enemies"))
        log(f"Enemy behaviour: {len(result.enemies)} enemy types randomized "
            f"({sum(bool(r.speed) for r in result.enemies)} with new movement)")

    if preset.weapons.enabled:
        settings = preset.weapons
        config = WeaponConfig(tier_weights=tuple(settings.tier_weights), **{f: getattr(settings, f) for f in (
            "weapons", "shields", "moveset_chance", "effect_chance", "element_chance", "isolate_npcs",
            "write_descriptions")})
        result.weapons = randomize_weapons(session, config, random.Random(f"{seed}-weapons"))
        log(f"Weapons: {len(result.weapons)} randomized ({sum(r.shield for r in result.weapons)} shields, "
            f"{sum(bool(r.moveset_from) for r in result.weapons)} new movesets)")

    if preset.armor.enabled:
        settings = preset.armor
        config = ArmorConfig(tier_weights=tuple(settings.tier_weights), **{f: getattr(settings, f) for f in (
            "set_tiers", "effect_chance", "isolate_npcs", "write_descriptions")})
        result.armor = randomize_armor(session, config, random.Random(f"{seed}-armor"))
        log(f"Armor: {len(result.armor)} pieces randomized ({sum(bool(r.effects) for r in result.armor)} with effects)")

    if preset.appearance.enabled:
        settings = preset.appearance
        config = AppearanceConfig(settings.npc_faces, settings.player_faces, settings.physiques, settings.npc_bodies)
        result.appearance = randomize_appearance(session, config, random.Random(f"{seed}-appearance"))
        a = result.appearance
        log(f"Body and face: {len(a.npc_faces)} NPC faces, {len(a.player_faces)} face templates, "
            f"{len(a.physiques)} physiques, {len(a.npc_bodies)} NPC bodies")

    result.written = list(session.write({"seed": seed, "preset": preset.to_dict()}, out_dir=out_dir))
    result.target = out_dir if out_dir is not None else install.root
    log(f"Wrote {', '.join(result.written) or 'nothing'} to {result.target}")
    return result


def _result(session: Session, seed: int) -> RunResult:
    names = session.base.text.get(13, ("", {}))[1]
    spell_names = {**session.base.text.get(14, ("", {}))[1], **{k: v for k, v in session.base.text.get(118, ("", {}))[1].items() if v}}
    return RunResult(
        seed=seed,
        gameparam_base=session.gameparam_base.state,
        text_base=session.text_base.state,
        conflicts=session.conflicts,
        foreign=[d.summary() for d in session.foreign_changes()["params"]],
        ring_names=dict(names),
        spell_names=spell_names,
        armor_names={k: v for k, v in session.base.text.get(12, ("", {}))[1].items() if v},
        weapon_names={k: v for k, v in session.base.text.get(11, ("", {}))[1].items() if v},
        goods_names={**session.base.text.get(10, ("", {}))[1],
                     **{k: v for k, v in session.base.text.get(111, ("", {}))[1].items() if v}},
    )
