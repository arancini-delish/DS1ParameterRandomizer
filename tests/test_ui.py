"""UI smoke tests, rendered off screen."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from ds1rand.presets.schema import BUILTIN, Preset  # noqa: E402
from ds1rand.ui.app import CUSTOM, MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def window(app):
    window = MainWindow()
    window.apply_preset(BUILTIN["Standard"])
    yield window
    window.close()


def test_builtin_presets_set_the_ring_distribution(window):
    window.preset_combo.setCurrentText("Hard")
    assert window.rings_tab.distribution.values() == BUILTIN["Hard"].rings.tier_weights


def test_editing_switches_to_custom(window):
    window.rings_tab.distribution.spins[0].setValue(0.5)
    assert window.preset_combo.currentText() == CUSTOM
    assert window.rings_tab.distribution.preset_combo.currentText() == "Custom"


def test_share_string_round_trip(window):
    window.seed.setText("123")
    window.rings_tab.isolate_npcs.setChecked(False)
    preset = Preset.from_share_string(window.current_preset().to_share_string())
    window.apply_preset(BUILTIN["Easy"])
    window.apply_preset(preset)
    assert window.current_preset().seed == 123 and window.rings_tab.isolate_npcs.isChecked() is False


def test_disabling_rings_disables_their_options(window):
    window.rings_tab.enabled.setChecked(False)
    assert not window.rings_tab.options.isEnabled() and window.current_preset().rings.enabled is False


def test_spells_tab(window):
    window.preset_combo.setCurrentText("Misery")
    assert window.spells_tab.distribution.values() == BUILTIN["Misery"].spells.tier_weights
    window.spells_tab.status_chance.setValue(40)
    assert window.preset_combo.currentText() == CUSTOM
    assert window.current_preset().spells.status_chance == 0.4


def test_projectiles_tab(window):
    window.preset_combo.setCurrentText("Hard")
    tab = window.projectiles_tab
    assert tab.distributions["player"].values() == BUILTIN["Hard"].projectiles.player_weights
    assert tab.distributions["enemy"].values() == BUILTIN["Hard"].projectiles.enemy_weights
    tab.owner_boxes["environment"].setChecked(False)
    tab.cross_enemy.setChecked(False)
    assert window.preset_combo.currentText() == CUSTOM
    settings = window.current_preset().projectiles
    assert settings.environment is False and settings.cross_enemy is False


def test_enemies_tab(window):
    window.preset_combo.setCurrentText("Misery")
    tab = window.enemies_tab
    assert tab.distribution.values() == BUILTIN["Misery"].enemies.tier_weights
    tab.boxes["bosses"].setChecked(True)
    tab.boxes["speed"].setChecked(False)
    assert window.preset_combo.currentText() == CUSTOM
    settings = window.current_preset().enemies
    assert settings.bosses is True and settings.speed is False


def test_weapons_tab(window):
    window.preset_combo.setCurrentText("Easy")
    tab = window.weapons_tab
    assert tab.distribution.values() == BUILTIN["Easy"].weapons.tier_weights
    tab.shields.setChecked(False)
    tab.moveset_chance.setValue(60)
    assert window.preset_combo.currentText() == CUSTOM
    settings = window.current_preset().weapons
    assert settings.shields is False and settings.moveset_chance == 0.6
