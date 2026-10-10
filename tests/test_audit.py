"""Spoiler log and catalogue inspection (Phase 7), on the real install with GameParam/item text redirected."""
import random

from ds1rand.catalogue.inspect import coverage, describe_row
from ds1rand.features.weapons import WeaponConfig, randomize_weapons
from ds1rand.presets.schema import BUILTIN, Preset
from ds1rand.run import run
from ds1rand.session import Session
from ds1rand.spoiler import SPOILER_FILE


def test_describe_row(redirected_install):
    session = Session.open(redirected_install)
    report = describe_row(session, "Magic", 3000)
    assert report.exists and report.name == "Soul Arrow" and "player_spell" in report.features
    assert any(r.node == f"Bullet:{session.base.params['Magic'].row_values(3000)['refId']}" for r in report.refs)
    assert any(r.node.startswith("EquipParamGoods:") for r in report.users)
    assert report.subtype and not report.changes
    assert not describe_row(session, "Magic", 123456789).exists


def test_inspection_shows_this_runs_changes(redirected_install):
    session = Session.open(redirected_install)
    result = next(r for r in randomize_weapons(session, WeaponConfig(), random.Random(1)) if r.effects)
    report = describe_row(session, "EquipParamWeapon", result.weapon_id)
    assert set(result.changes) <= set(report.changes)
    name, (vanilla, base, now) = next(iter(report.changes.items()))
    assert now == session.store.values("EquipParamWeapon", result.weapon_id)[name]
    new_speffect = next(v for f, (_, _, v) in report.changes.items() if f.startswith(("spEffect", "resident")))
    assert describe_row(session, "SpEffectParam", new_speffect).new
    table = {c.param: c for c in coverage(session)}
    assert table["EquipParamWeapon"].changed > 1000 and table["Bullet"].used > 400


def test_run_writes_a_spoiler_log(redirected_install, tmp_path):
    preset = Preset.from_dict(BUILTIN["Standard"].to_dict())
    preset.seed = 7
    result = run(preset, redirected_install, out_dir=tmp_path / "out", log=lambda _: None)
    text = (tmp_path / "out" / SPOILER_FILE).read_text(encoding="utf-8")
    assert result.spoiler == tmp_path / "out" / SPOILER_FILE
    assert "Seed: 7" in text and preset.to_share_string() in text
    for section in ("Rings", "Spells", "Projectiles", "Enemy behaviour", "Weapons", "Armor", "Body and face"):
        assert f"\n{section}\n" in text
    ring = result.rings[0]
    assert f"{result.ring_names[ring.ring_id]} [{ring.tier.name.title()}]" in text
    quiet = run(preset, redirected_install, out_dir=tmp_path / "quiet", log=lambda _: None, spoiler=False)
    assert quiet.spoiler is None and not (tmp_path / "quiet" / SPOILER_FILE).exists()
