"""The shared run pipeline (CLI and UI), on the real install's game files with GameParam/item text redirected."""
from ds1rand.io.msg import ItemText
from ds1rand.presets.schema import BUILTIN, Preset
from ds1rand.run import run, validate


def test_validate_changes_nothing(redirected_install):
    before = redirected_install.gameparam.read_bytes()
    result = validate(redirected_install)
    assert result.gameparam_base == "external" and result.foreign == []
    assert redirected_install.gameparam.read_bytes() == before


def test_run_from_preset(redirected_install, tmp_path):
    preset = Preset.from_dict(BUILTIN["Easy"].to_dict())
    preset.seed = 5
    logs = []
    result = run(preset, redirected_install, out_dir=tmp_path / "out", log=logs.append)
    assert result.seed == 5 and len(result.rings) == 35 and result.spells and result.projectiles and result.enemies and result.weapons and result.armor and result.appearance
    text = ItemText.from_path(tmp_path / "out" / "msg" / "ENGLISH" / "item.msgbnd.dcx")
    ring = result.rings[0]
    assert text.get("Accessory_description", ring.ring_id) == ", ".join(ring.summaries)
    assert any("Rings: 35 randomized" in line for line in logs)
    again = run(preset, redirected_install, out_dir=tmp_path / "again", log=lambda _: None)
    assert [r.effects for r in again.rings] == [r.effects for r in result.rings]


def test_rings_disabled_writes_nothing(redirected_install, tmp_path):
    preset = Preset.from_dict(BUILTIN["Standard"].to_dict())
    preset.rings.enabled = False
    preset.spells.enabled = False
    preset.projectiles.enabled = False
    preset.enemies.enabled = False
    preset.weapons.enabled = False
    preset.armor.enabled = False
    preset.appearance.enabled = False
    result = run(preset, redirected_install, out_dir=tmp_path / "out", log=lambda _: None)
    assert result.written == [] and result.rings == []


def test_features_use_independent_random_streams(redirected_install, tmp_path):
    preset = Preset.from_dict(BUILTIN["Standard"].to_dict())
    preset.seed = 9
    both = run(preset, redirected_install, out_dir=tmp_path / "both", log=lambda _: None)
    preset.spells.enabled = False
    rings_only = run(preset, redirected_install, out_dir=tmp_path / "rings", log=lambda _: None)
    assert [r.effects for r in both.rings] == [r.effects for r in rings_only.rings]
    assert [(r.slot.row, r.tier, r.donor) for r in both.projectiles] ==         [(r.slot.row, r.tier, r.donor) for r in rings_only.projectiles]
    assert [(r.npc_id, r.factors) for r in both.enemies] == [(r.npc_id, r.factors) for r in rings_only.enemies]
    # New effect rows get IDs after whatever other features allocated, so compare everything else.
    def weapons(result):
        return [(r.weapon_id, r.tier, r.effects, {k: v for k, v in r.changes.items() if not k.startswith(("spEffectBehaviorId", "residentSpEffectId"))})
                for r in result.weapons]
    assert weapons(both) == weapons(rings_only)


def test_weapon_seed_changes_only_the_weapons(redirected_install, tmp_path):
    """Two players sharing a seed but not a weapon seed: identical everything except weapon rows, the effect rows
    weapons add (allocated last, so nothing else shifts) and weapon descriptions."""
    from ds1rand.features.weapons import ON_HIT, WHILE_HELD

    def changes(weapon_seed, name):
        preset = Preset.from_dict(BUILTIN["Standard"].to_dict())
        preset.seed = 3
        preset.weapons.seed = weapon_seed
        result = run(preset, redirected_install, out_dir=tmp_path / name, log=lambda _: None, spoiler=False)
        changed = result.session.store.changes()
        weapon_effects = {w.changes[f] for w in result.weapons for f in ON_HIT + WHILE_HELD if f in w.changes}
        changed["SpEffectParam"] = {k: v for k, v in changed["SpEffectParam"].items() if k not in weapon_effects}
        text = {k: v for k, v in result.session.text.items() if k[0] != "Weapon_long_desc"}
        return changed, text, [(w.weapon_id, w.tier, w.changes.get("attackBasePhysics")) for w in result.weapons]
    a, text_a, weapons_a = changes(101, "a")
    b, text_b, weapons_b = changes(202, "b")
    assert weapons_a != weapons_b
    assert set(a) == set(b) and text_a == text_b
    for param in a:
        if param != "EquipParamWeapon":
            assert a[param] == b[param], param
