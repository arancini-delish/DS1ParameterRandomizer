"""Bullet and Magic subtype classification (Phase 4b). Runs on the committed baseline; no install needed."""
import pytest

from ds1rand.baseline.store import Baseline
from ds1rand.catalogue.subtypes import CAST_ANIMATIONS, bullet_chain, classify_bullet, classify_magic, coverage
from ds1rand.catalogue.usage import compute_usage
from ds1rand.graph.build import build_graph


@pytest.fixture(scope="module")
def baseline():
    return Baseline.load()


@pytest.fixture(scope="module")
def used(baseline):
    usage = compute_usage(build_graph(baseline), baseline)
    return {p: sorted(n.id for n in usage if n.name == p) for p in ("Bullet", "Magic")}


def chain_subtypes(baseline, magic_id):
    first = baseline.params["Magic"].row_values(magic_id)["refId"]
    return [classify_bullet(baseline.params["Bullet"].row_values(b)).subtype for b in bullet_chain(baseline, first)]


@pytest.mark.parametrize("magic_id, subtype, delivery", [
    (3000, "sorcery/projectile", "bullet"),  # Soul Arrow
    (3100, "sorcery/weapon_buff", "speffect"),  # Magic Weapon
    (4050, "pyromancy/spray", "bullet"),  # Fire Surge
    (4200, "pyromancy/mist", "bullet"),  # Poison Mist
    (4030, "pyromancy/ground_eruption", "bullet"),  # Firestorm
    (5000, "miracle/self_miracle", "speffect"),  # Heal
    (5500, "miracle/spear_throw", "bullet"),  # Lightning Spear
])
def test_spell_subtypes(baseline, magic_id, subtype, delivery):
    spell = classify_magic(baseline, magic_id)
    assert (spell.subtype, spell.delivery) == (subtype, delivery)


def test_bullet_chains(baseline):
    assert chain_subtypes(baseline, 3040) == ["orbit_multi", "homing"]  # Homing Soulmass orbs fire homing shots
    assert chain_subtypes(baseline, 4200)[1] == "stationary_lingering"  # Poison Mist cloud
    assert chain_subtypes(baseline, 4050) == ["homing_stream"]  # Fire Surge
    assert len(chain_subtypes(baseline, 3700)) == 16  # White Dragon Breath ground trace


def test_payload(baseline):
    soul_arrow = classify_bullet(baseline.params["Bullet"].row_values(3000))
    assert soul_arrow.payload == ("damage",)


def test_every_used_row_is_classified(baseline, used):
    result = coverage(baseline, used)
    assert sum(result["Bullet"].values()) == len(used["Bullet"]) == 514
    assert sum(result["Magic"].values()) == len(used["Magic"]) == 104
    assert not [s for s in result["Magic"] if "unknown" in s]


def test_every_cast_category_in_use_is_named(baseline):
    magic = baseline.params["Magic"]
    assert {magic.row_values(r)["refType"] for r in magic.rows if r} <= set(CAST_ANIMATIONS)
