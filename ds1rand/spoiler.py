"""Spoiler / changes log of a run: a plain-text file listing what every feature did.

`run` writes it as `ds1rand-spoiler.txt` next to the output (the output folder, or the game folder when writing in
place), unless turned off. It starts with the seed, preset and share string (enough to reproduce the run), what other
mods had changed, then one section per enabled feature.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ds1rand.defs.meta import load_row_names

if TYPE_CHECKING:
    from ds1rand.presets.schema import Preset
    from ds1rand.run import RunResult

SPOILER_FILE = "ds1rand-spoiler.txt"
WEAPON_FIELDS = {
    "attackBasePhysics": "phys", "attackBaseMagic": "mag", "attackBaseFire": "fire", "attackBaseThunder": "ltng",
    "correctStrength": "Str", "correctAgility": "Dex", "correctMagic": "Int", "correctFaith": "Fai",
    "properStrength": "req Str", "properAgility": "req Dex", "properMagic": "req Int", "properFaith": "req Fai",
    "weight": "weight", "physGuardCutRate": "phys block", "staminaGuardDef": "stability",
}
ARMOR_FIELDS = {
    "defensePhysics": "phys", "defenseSlash": "slash", "defenseBlow": "strike", "defenseThrust": "thrust",
    "defenseMagic": "mag", "defenseFire": "fire", "defenseThunder": "ltng", "saDurability": "poise",
    "resistPoison": "poison", "resistDisease": "toxic", "resistBlood": "bleed", "resistCurse": "curse",
    "weight": "weight",
}


def _fmt(value) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


def _effect(speffect: int) -> str:
    name = load_row_names("SpEffectParam").get(speffect)
    return f"status effect {speffect}" + (f" ({name})" if name else "")


def _section(title: str, lines: list[str]) -> list[str]:
    return ["", title, "=" * len(title), *(lines or ["(nothing changed)"])]


def spoiler_text(preset: Preset, result: RunResult) -> str:
    lines = [
        "ds1rand spoiler log",
        f"Generated {datetime.now():%Y-%m-%d %H:%M}",
        f"Seed: {result.seed}",
        f"Preset: {preset.name}",
        f"Share string: {preset.to_share_string()}",
        f"GameParam base: {result.gameparam_base}; item text base: {result.text_base}",
        "Kept from other mods:", *[f"  {c}" for c in result.foreign or ["nothing"]],
    ]
    if preset.rings.enabled:
        lines += _section("Rings", [
            f"{result.ring_names.get(r.ring_id) or r.ring_id} [{r.tier.name.title()}]: {', '.join(r.summaries)}"
            for r in result.rings])
    if preset.spells.enabled:
        def spell(magic_id):
            return result.spell_names.get(magic_id) or f"NPC spell {magic_id}"
        rows = []
        for s in result.spells:
            extras = [f"payload of {spell(s.donor)}"]
            if s.owner == "player":
                extras.append(f"{s.casts} casts, {s.slots} slot(s), requirement {s.requirement}")
            if s.visual_from:
                extras.append(f"looks like {spell(s.visual_from)}")
            if s.motion:
                extras.append(s.motion)
            if s.chained_from:
                extras.append(f"chains into {spell(s.chained_from[0])}")
            if s.status:
                extras.append(f"adds {_effect(s.status)}")
            rows.append(f"{spell(s.magic_id)} ({s.owner}) [{s.tier.name.title()}, power {s.power:.2f}]: "
                        + "; ".join(extras))
        lines += _section("Spells", rows)
    if preset.projectiles.enabled:
        bullets = load_row_names("Bullet")
        rows = []
        for p in result.projectiles:
            slot = p.slot
            name = (result.goods_names.get(slot.row) if slot.kind == "throwable" else None) \
                or f"{slot.kind.replace('_', ' ')} {slot.group if slot.kind == 'enemy' else ''} behavior {slot.row}"
            extras = [f"fires {bullets.get(p.donor, p.donor)}"]
            if p.carry:
                extras.append(f"carry {p.carry}")
            if p.visual_from:
                extras.append(f"looks like {bullets.get(p.visual_from, p.visual_from)}")
            if p.motion:
                extras.append(p.motion)
            if p.chained_from:
                extras.append(f"chains into {bullets.get(p.chained_from[1], p.chained_from[1])}")
            if p.status:
                extras.append(f"adds {_effect(p.status)}")
            rows.append(f"{' '.join(name.split())} [{p.tier.name.title()}, power {p.power:.2f}]: " + "; ".join(extras))
        lines += _section("Projectiles", rows)
    if preset.enemies.enabled:
        lines += _section("Enemy behaviour", [
            f"{e.name or e.model} (NpcParam {e.npc_id}, {e.category}) [{e.tier.name.title()}]: "
            + ", ".join(f"{g} x{f:.2f}" for g, f in e.factors.items()) + (f"; moves {e.speed}" if e.speed else "")
            for e in result.enemies])
    if preset.weapons.enabled:
        rows = []
        for w in result.weapons:
            name = result.weapon_names.get(w.weapon_id) or str(w.weapon_id)
            stats = ", ".join(f"{label} {_fmt(w.changes[f])}" for f, label in WEAPON_FIELDS.items() if f in w.changes)
            moveset = f"; moves like {result.weapon_names.get(w.moveset_from, w.moveset_from)}" if w.moveset_from else ""
            effects = f"; {'; '.join(w.effects)}" if w.effects else ""
            rows.append(f"{name} [{w.tier.name.title()}, value {w.value:.2f}]: {stats or 'stats as vanilla'}"
                        f"{moveset}{effects}")
        lines += _section("Weapons", rows)
    if preset.armor.enabled:
        rows = []
        for a in result.armor:
            name = result.armor_names.get(a.armor_id) or str(a.armor_id)
            stats = ", ".join(f"{label} {_fmt(a.changes[f])}" for f, label in ARMOR_FIELDS.items() if f in a.changes)
            effects = f"; {'; '.join(a.effects)}" if a.effects else ""
            rows.append(f"{name} [{a.tier.name.title()}, rating {a.value:.2f}]: {stats or 'stats as vanilla'}{effects}")
        lines += _section("Armor", rows)
    if preset.appearance.enabled and result.appearance is not None:
        a, s = result.appearance, preset.appearance
        lines += _section("Body and face", [
            f"NPC faces: {len(a.npc_faces)} at {s.npc_faces:.0%}",
            f"Face templates: {len(a.player_faces)} at {s.player_faces:.0%}",
            f"Physiques: {len(a.physiques)} at {s.physiques:.0%}",
            f"NPC bodies: {len(a.npc_bodies)} at {s.npc_bodies:.0%}",
        ])
    return "\n".join(lines) + "\n"


def write_spoiler(preset: Preset, result: RunResult, directory: Path) -> Path:
    path = Path(directory) / SPOILER_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(spoiler_text(preset, result), encoding="utf-8")
    return path
