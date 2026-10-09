"""Ring randomizer (Phase 6.1). Uses the real install's game files with GameParam/item text redirected to copies."""
import random

import pytest

from ds1rand.features.rings import (
    DEFAULT_PINNED, EFFECTS, PRESETS, RingConfig, Tier, randomize_rings, ring_template, summary,
)
from ds1rand.io.gameparam import GameParams
from ds1rand.io.msg import ItemText
from ds1rand.session import Session


@pytest.fixture
def session(redirected_install):
    return Session.open(redirected_install)


def run(session, seed=1, **config):
    return randomize_rings(session, RingConfig(**config), random.Random(seed))


def test_every_effect_field_has_a_summary():
    for effects in EFFECTS.values():
        for effect in effects:
            for f, v in zip(effect.fields, effect.values):
                assert summary(f, v)


def test_template_is_a_ring_without_effects(session):
    template = ring_template(session)
    assert template["effectEndurance"] == -1.0  # rings last while worn
    assert template["physicsDiffence"] == 0 and template["stateInfo"] == 0


def test_rings_are_randomized_except_pinned(session):
    results = run(session)
    assert {r.ring_id for r in results} == {r for r in session.base.params["EquipParamAccessory"].rows if r} - DEFAULT_PINNED
    for r in results:
        values = session.store.values("SpEffectParam", r.speffect_id)
        assert all(values[f] == v for f, v in r.effects.items())
        assert session.text[("Accessory_description", r.ring_id)] == ", ".join(r.summaries)
    pinned_effects = {session.base.params["EquipParamAccessory"].row_values(r)["refId"] for r in DEFAULT_PINNED}
    assert not pinned_effects & set(session.store.changes().get("SpEffectParam", {}))


def test_same_seed_same_rings(redirected_install):
    first = run(Session.open(redirected_install))
    second = run(Session.open(redirected_install))
    assert [(r.ring_id, r.tier, r.effects) for r in first] == [(r.ring_id, r.tier, r.effects) for r in second]


def test_npc_phantoms_keep_vanilla_rings(session):
    havel = session.base.params["EquipParamAccessory"].row_values(100)["refId"]
    run(session)
    # Havel's Ring keeps its ID; its effect row is replaced by a copy only the player's ring uses.
    new_effect = session.store.values("EquipParamAccessory", 100)["refId"]
    assert new_effect != havel
    assert session.store.values("SpEffectParam", havel) == session.base.params["SpEffectParam"].row_values(havel)


def test_tier_weights(session):
    results = run(session, tier_weights=(0, 0, 0, 1))
    assert {r.tier for r in results} == {Tier.LEGENDARY}


def test_write_and_read_back(redirected_install):
    session = Session.open(redirected_install)
    results = run(session, tier_weights=PRESETS["Easy"])
    session.write({"seed": 1})
    params = GameParams.from_path(redirected_install.gameparam)
    text = ItemText.from_path(redirected_install.item_msgbnd)
    for r in results:
        effect = params.row_values("EquipParamAccessory", r.ring_id)["refId"]
        written = params.row_values("SpEffectParam", effect)
        assert {f: written[f] for f in r.effects} == pytest.approx(r.effects)  # fields are float32 in the file
        assert text.get("Accessory_description", r.ring_id) == ", ".join(r.summaries)
