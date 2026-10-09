import json

import pytest

from ds1rand.presets.schema import BUILTIN, VERSION, Preset, RingsSettings


def test_json_and_share_string_round_trip(tmp_path):
    preset = Preset(name="Custom", seed=42, rings=RingsSettings(True, (0.1, 0.2, 0.3, 0.4), False, True))
    assert Preset.from_json(preset.to_json()) == preset
    assert Preset.from_share_string(preset.to_share_string()) == preset
    path = tmp_path / "preset.json"
    preset.save(path)
    assert Preset.load(path) == preset


def test_share_string_shape():
    text = BUILTIN["Standard"].to_share_string()
    assert text.startswith(f"DS1R{VERSION}-") and len(text) < 400
    with pytest.raises(ValueError):
        Preset.from_share_string("hello")


def test_old_or_partial_presets_load_with_defaults():
    preset = Preset.from_dict({"version": 1, "rings": {"enabled": False, "someFutureOption": 3}})
    assert preset.rings.enabled is False and preset.rings.isolate_npcs is True and preset.seed is None


def test_newer_versions_are_refused():
    with pytest.raises(ValueError, match="newer"):
        Preset.from_dict({"version": VERSION + 1})


def test_builtins_cover_ring_presets():
    assert set(BUILTIN) == {"Easy", "Standard", "Hard", "Misery"}
    assert json.loads(BUILTIN["Hard"].to_json())["rings"]["tier_weights"] == [0.85, 0.1, 0.04, 0.01]
