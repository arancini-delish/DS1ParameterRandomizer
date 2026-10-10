"""Body and face randomizer (Phase 6.7): NPC faces, character creation face templates, physiques and NPC bodies.

Each part has a strength from 0 (vanilla) to 1. Every value moves `strength` of the way from its vanilla value to a
random value within that field's vanilla extremes (the min-max over all vanilla rows), so full strength draws every
value anew within sensible limits. Choice fields (hair style) switch to another vanilla choice with probability
`strength`.

    NPC faces           FaceGenParam rows NPC characters use (`CharaInitParam.npcPlayerFaceGenId`)
    player faces        the character creation face templates (CharaInitParam 2300-2319 -> FaceGenParam 1000-1009
                        male, 2000-2009 female); existing saves keep their face
    physiques           the nine physique options' body scales (CharaInitParam 2100-2108 male, 2200-2208 female):
                        each option gets its own random set of changes; existing saves keep their body
    NPC bodies          body scales of NPC characters (rows with a face)

A face row shared by a template and an NPC (vanilla: FaceGenParam 2000) is copied for the NPC, so the two strengths
stay independent.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from ds1rand.session import Session

TEMPLATES = range(2300, 2320)
PHYSIQUES = (*range(2100, 2109), *range(2200, 2209))
CHARACTER_CREATION = range(2100, 2400)  # physique, face template and preview rows
BODY = ("bodyScaleHead", "bodyScaleBreast", "bodyScaleAbdomen", "bodyScaleArm", "bodyScaleLeg")
BODY_LIMITS = (-100, 100)
CHOICE_FIELDS = frozenset({"hairStyle"})


@dataclass
class AppearanceConfig:
    npc_faces: float = 0.5
    player_faces: float = 0.5
    physiques: float = 0.5
    npc_bodies: float = 0.5


@dataclass
class AppearanceResult:
    npc_faces: list[int] = field(default_factory=list)  # FaceGenParam rows
    player_faces: list[int] = field(default_factory=list)
    physiques: list[int] = field(default_factory=list)  # CharaInitParam rows
    npc_bodies: list[int] = field(default_factory=list)


def _blend(rng: random.Random, value, low, high, strength: float, is_int: bool):
    target = rng.uniform(low, high)
    new = value + strength * (target - value)
    return int(round(new)) if is_int else new


def randomize_appearance(session: Session, config: AppearanceConfig, rng: random.Random) -> AppearanceResult:
    faces = session.base.params["FaceGenParam"]
    chara = session.base.params["CharaInitParam"]
    store = session.store
    result = AppearanceResult()

    fields = list(faces.row_values(min(faces.rows)))
    vanilla = session.vanilla.params["FaceGenParam"]
    columns = {f: [vanilla.row_values(r)[f] for r in vanilla.rows] for f in fields}
    limits = {f: (min(v), max(v)) for f, v in columns.items()}
    choices = {f: sorted(set(columns[f])) for f in CHOICE_FIELDS}

    templates = {chara.row_values(r)["npcPlayerFaceGenId"] for r in TEMPLATES if r in chara.rows}
    templates = {t for t in templates if t in faces.rows}
    npc_rows = [r for r in sorted(chara.rows)
                if r not in CHARACTER_CREATION and chara.row_values(r)["npcPlayerFaceGenId"] in faces.rows]

    def face(row_id: int, strength: float) -> None:
        values = store.values("FaceGenParam", row_id)
        updates = {}
        for name in fields:
            low, high = limits[name]
            if name in CHOICE_FIELDS:
                if rng.random() < strength:
                    updates[name] = rng.choice(choices[name])
            elif low < high:
                updates[name] = _blend(rng, values[name], low, high, strength, isinstance(values[name], int))
        store.set("FaceGenParam", row_id, updates)

    # NPC faces: NPCs sharing a template's face get their own copy first.
    npc_faces: dict[int, int] = {}
    for row_id in npc_rows:
        face_id = chara.row_values(row_id)["npcPlayerFaceGenId"]
        if face_id in templates and config.npc_faces > 0:
            if face_id not in npc_faces:
                npc_faces[face_id] = session.ids.allocate("FaceGenParam")
                store.add("FaceGenParam", npc_faces[face_id], copy_from=face_id)
            store.set("CharaInitParam", row_id, {"npcPlayerFaceGenId": npc_faces[face_id]})
        else:
            npc_faces.setdefault(face_id, face_id)
    if config.npc_faces > 0:
        for original, row_id in sorted(npc_faces.items()):
            face(row_id, config.npc_faces)
            result.npc_faces.append(row_id)
    if config.player_faces > 0:
        for row_id in sorted(templates):
            face(row_id, config.player_faces)
            result.player_faces.append(row_id)

    def body(row_id: int, strength: float) -> None:
        values = store.values("CharaInitParam", row_id)
        store.set("CharaInitParam", row_id,
                  {f: _blend(rng, values[f], *BODY_LIMITS, strength, True) for f in BODY})

    if config.physiques > 0:
        for row_id in PHYSIQUES:
            if row_id in chara.rows:
                body(row_id, config.physiques)
                result.physiques.append(row_id)
    if config.npc_bodies > 0:
        for row_id in npc_rows:
            body(row_id, config.npc_bodies)
            result.npc_bodies.append(row_id)
    return result
