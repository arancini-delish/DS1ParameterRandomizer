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
    assert result.seed == 5 and len(result.rings) == 36 and result.spells
    text = ItemText.from_path(tmp_path / "out" / "msg" / "ENGLISH" / "item.msgbnd.dcx")
    ring = result.rings[0]
    assert text.get("Accessory_description", ring.ring_id) == ", ".join(ring.summaries)
    assert any("Rings: 36 randomized" in line for line in logs)
    again = run(preset, redirected_install, out_dir=tmp_path / "again", log=lambda _: None)
    assert [r.effects for r in again.rings] == [r.effects for r in result.rings]


def test_rings_disabled_writes_nothing(redirected_install, tmp_path):
    preset = Preset.from_dict(BUILTIN["Standard"].to_dict())
    preset.rings.enabled = False
    preset.spells.enabled = False
    result = run(preset, redirected_install, out_dir=tmp_path / "out", log=lambda _: None)
    assert result.written == [] and result.rings == []


def test_features_use_independent_random_streams(redirected_install, tmp_path):
    preset = Preset.from_dict(BUILTIN["Standard"].to_dict())
    preset.seed = 9
    both = run(preset, redirected_install, out_dir=tmp_path / "both", log=lambda _: None)
    preset.spells.enabled = False
    rings_only = run(preset, redirected_install, out_dir=tmp_path / "rings", log=lambda _: None)
    assert [r.effects for r in both.rings] == [r.effects for r in rings_only.rings]
