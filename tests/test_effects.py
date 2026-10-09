"""SpEffect and AtkParam classification (Phase 4b part 2). Runs on the committed baseline; no install needed."""
import pytest

from ds1rand.baseline.store import Baseline
from ds1rand.catalogue.effects import EffectClassifier
from ds1rand.graph.build import build_graph


@pytest.fixture(scope="module")
def classifier():
    baseline = Baseline.load()
    return EffectClassifier(baseline, build_graph(baseline))


@pytest.mark.parametrize("row_id, subtype", [
    (2000, "ring/movement"),  # Havel's Ring: equip load
    (2020, "ring/defense"),
    (1400, "spell/regen"),  # Heal
    (5295, "on_hit/status"),  # curse build-up on hit
    (9600, "engine/marker"),  # level sync flag
])
def test_speffect_subtypes(classifier, row_id, subtype):
    assert classifier.speffect(row_id).subtype == subtype


def test_engine_states_are_kept_separately(classifier):
    # Payload decides the kind, but the stateInfo the engine implements is recorded so swaps can preserve it.
    effect = classifier.speffect(2010)
    assert (effect.kind, effect.state) == ("attack", "48")
    assert classifier.speffect(33).state == "Petrify"


def test_rings_with_engine_states(classifier):
    rings = [classifier.speffect(r) for r in range(2000, 2500) if r in classifier.baseline.params["SpEffectParam"].rows]
    ring_states = {e.state for e in rings if e.contexts[:1] == ("ring",) and e.kind.startswith("state:")}
    assert "Ring resurrection when normally dead" in ring_states  # Ring of Sacrifice


def test_every_speffect_is_classified(classifier):
    rows = [r for r in classifier.baseline.params["SpEffectParam"].rows if r]
    classes = [classifier.speffect(r) for r in rows]
    assert all(c.kind for c in classes)
    assert sum(1 for c in classes if not c.contexts) == 334  # unreferenced rows (AUDIT 14)


def test_attack_subtypes(classifier):
    soul_arrow_attack = classifier.baseline.params["Bullet"].row_values(3000)["atkId_Bullet"]
    assert classifier.attack("AtkParam_Pc", soul_arrow_attack) == "bullet/magic"
    subtypes = {classifier.attack("AtkParam_Pc", r) for r in classifier.baseline.params["AtkParam_Pc"].rows if r}
    assert "behavior/weapon_scaled" in subtypes  # melee swings scale the wielded weapon
