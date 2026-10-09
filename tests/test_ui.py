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
