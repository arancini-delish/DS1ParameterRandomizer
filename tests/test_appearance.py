"""Body and face randomizer (Phase 6.7). Uses the real install's game files with GameParam/item text redirected."""
import random

import pytest

from ds1rand.features.appearance import (
    BODY, BODY_LIMITS, PHYSIQUES, TEMPLATES, AppearanceConfig, randomize_appearance,
)
from ds1rand.session import Session


@pytest.fixture
def session(redirected_install):
    return Session.open(redirected_install)


def run(session, *strengths, seed=1):
    return randomize_appearance(session, AppearanceConfig(*strengths), random.Random(seed))


def test_zero_strength_changes_nothing(session):
    run(session, 0, 0, 0, 0)
    assert not session.store.changes()


def test_full_strength_stays_within_vanilla_extremes(session):
    result = run(session, 1, 1, 1, 1)
    vanilla = session.vanilla.params["FaceGenParam"]
    fields = list(vanilla.row_values(min(vanilla.rows)))
    limits = {f: (min(vanilla.row_values(r)[f] for r in vanilla.rows),
                  max(vanilla.row_values(r)[f] for r in vanilla.rows)) for f in fields}
    for row_id in result.npc_faces + result.player_faces:
        values = session.store.values("FaceGenParam", row_id)
        assert all(limits[f][0] <= values[f] <= limits[f][1] for f in fields)
    for row_id in result.physiques + result.npc_bodies:
        values = session.store.values("CharaInitParam", row_id)
        assert all(BODY_LIMITS[0] <= values[f] <= BODY_LIMITS[1] for f in BODY)
    assert len(result.player_faces) == 20 and len(result.physiques) == len(PHYSIQUES)
    assert len(result.npc_faces) > 50 and len(result.npc_bodies) > 150


def test_strength_controls_how_far_values_move(session, redirected_install):
    def distance(strength):
        s = Session.open(redirected_install)
        result = run(s, 0, 0, strength, 0)
        chara = s.base.params["CharaInitParam"]
        return sum(abs(s.store.values("CharaInitParam", r)[f] - chara.row_values(r)[f])
                   for r in result.physiques for f in BODY)
    assert 0 < distance(0.2) < distance(1.0)


def test_parts_are_independent(session):
    result = run(session, 0, 1, 0, 0)
    chara = session.base.params["CharaInitParam"]
    templates = {chara.row_values(r)["npcPlayerFaceGenId"] for r in TEMPLATES}
    assert set(result.player_faces) == templates
    assert set(session.store.changes()) == {"FaceGenParam"}


def test_npcs_sharing_a_template_face_get_a_copy(session):
    result = run(session, 1, 0, 0, 0)
    chara = session.base.params["CharaInitParam"]
    templates = {chara.row_values(r)["npcPlayerFaceGenId"] for r in TEMPLATES}
    assert not templates & set(session.store.changes().get("FaceGenParam", {}))
    copies = [r for r in result.npc_faces if session.store.is_new("FaceGenParam", r)]
    assert copies  # vanilla: FaceGenParam 2000 is a template and an NPC's face
    for row_id, values in session.store.changes()["CharaInitParam"].items():
        assert values["npcPlayerFaceGenId"] in copies
