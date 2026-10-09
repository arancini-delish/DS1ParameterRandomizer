"""The ds1rand window (Phase 7 prototype).

Top: global preset (built-ins, Custom), import/export of preset files and share strings, game folder, seed, output.
Tabs: one per feature (Rings, Spells; Projectiles and Enemy Behaviour arrive with Phase 6) and Install (what the
run would build on: other mods' changes, previous ds1rand output). Bottom: Validate / Randomize and the log.
Work runs in a background thread so the window stays responsive.
"""
from __future__ import annotations

import random
import traceback
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ds1rand.features.rings import PRESETS as RING_PRESETS
from ds1rand.features.rings import Tier
from ds1rand.features.spells import PRESETS as SPELL_PRESETS
from ds1rand.features.spells import SpellTier
from ds1rand.io.install import GameInstall
from ds1rand.presets.schema import BUILTIN, Preset, RingsSettings, SpellsSettings
from ds1rand.run import DEFAULT_OUT, RunResult, run, validate
from ds1rand.ui.widgets import DistributionEditor

CUSTOM = "Custom"


class _Worker(QtCore.QObject):
    log = QtCore.Signal(str)
    finished = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, job):
        super().__init__()
        self._job = job

    @QtCore.Slot()
    def start(self):
        try:
            self.finished.emit(self._job(self.log.emit))
        except Exception:  # shown to the user, not raised into Qt
            self.failed.emit(traceback.format_exc())


class RingsTab(QtWidgets.QWidget):
    changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        self.enabled = QtWidgets.QCheckBox("Randomize rings")
        self.enabled.toggled.connect(self._toggled)
        layout.addWidget(self.enabled)

        self.options = QtWidgets.QGroupBox("Ring tier distribution")
        options = QtWidgets.QVBoxLayout(self.options)
        self.distribution = DistributionEditor([t.name.title() for t in Tier], RING_PRESETS)
        self.distribution.changed.connect(self.changed)
        options.addWidget(self.distribution)
        self.isolate_npcs = QtWidgets.QCheckBox("NPC phantoms keep vanilla rings")
        self.write_summaries = QtWidgets.QCheckBox("Write ring effects into the item summaries")
        for box in (self.isolate_npcs, self.write_summaries):
            box.toggled.connect(self.changed)
            options.addWidget(box)
        layout.addWidget(self.options)

        self.results = QtWidgets.QTableWidget(0, 3)
        self.results.setHorizontalHeaderLabels(["Ring", "Tier", "Effects"])
        self.results.horizontalHeader().setStretchLastSection(True)
        self.results.verticalHeader().setVisible(False)
        self.results.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.results, stretch=1)

    def _toggled(self, checked: bool) -> None:
        self.options.setEnabled(checked)
        self.changed.emit()

    def settings(self) -> RingsSettings:
        return RingsSettings(self.enabled.isChecked(), self.distribution.values(), self.isolate_npcs.isChecked(),
                             self.write_summaries.isChecked())

    def apply(self, settings: RingsSettings) -> None:
        for widget in (self.enabled, self.isolate_npcs, self.write_summaries):
            widget.blockSignals(True)
        self.enabled.setChecked(settings.enabled)
        self.isolate_npcs.setChecked(settings.isolate_npcs)
        self.write_summaries.setChecked(settings.write_summaries)
        for widget in (self.enabled, self.isolate_npcs, self.write_summaries):
            widget.blockSignals(False)
        self.distribution.blockSignals(True)
        self.distribution.set_values(settings.tier_weights)
        self.distribution.blockSignals(False)
        self.options.setEnabled(settings.enabled)

    def show_results(self, result: RunResult) -> None:
        self.results.setRowCount(len(result.rings))
        for row, ring in enumerate(result.rings):
            name = result.ring_names.get(ring.ring_id, str(ring.ring_id))
            for col, text in enumerate((name, ring.tier.name.title(), ", ".join(ring.summaries))):
                self.results.setItem(row, col, QtWidgets.QTableWidgetItem(text))
        self.results.resizeColumnsToContents()


class SpellsTab(QtWidgets.QWidget):
    changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        self.enabled = QtWidgets.QCheckBox("Randomize spells")
        self.enabled.toggled.connect(self._toggled)
        layout.addWidget(self.enabled)

        self.options = QtWidgets.QGroupBox("Spell power distribution")
        options = QtWidgets.QVBoxLayout(self.options)
        self.distribution = DistributionEditor([t.name.title() for t in SpellTier], SPELL_PRESETS)
        self.distribution.changed.connect(self.changed)
        options.addWidget(self.distribution)
        self.player = QtWidgets.QCheckBox("Player spells")
        self.enemy = QtWidgets.QCheckBox("NPC caster spells")
        self.cross_school = QtWidgets.QCheckBox("Visuals may come from other schools")
        self.write_summaries = QtWidgets.QCheckBox("Write tier and casts into the spell summaries")
        for box in (self.player, self.enemy, self.cross_school, self.write_summaries):
            box.toggled.connect(self.changed)
            options.addWidget(box)
        chances = QtWidgets.QFormLayout()
        self.visual_chance = self._percent()
        self.status_chance = self._percent()
        chances.addRow("Chance of new visuals", self.visual_chance)
        chances.addRow("Chance of an added status effect", self.status_chance)
        options.addLayout(chances)
        layout.addWidget(self.options)

        self.results = QtWidgets.QTableWidget(0, 6)
        self.results.setHorizontalHeaderLabels(["Spell", "Owner", "Tier", "Casts", "Payload from", "Power"])
        self.results.horizontalHeader().setStretchLastSection(True)
        self.results.verticalHeader().setVisible(False)
        self.results.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.results, stretch=1)

    def _percent(self) -> QtWidgets.QSpinBox:
        spin = QtWidgets.QSpinBox()
        spin.setRange(0, 100)
        spin.setSuffix(" %")
        spin.valueChanged.connect(self.changed)
        return spin

    def _toggled(self, checked: bool) -> None:
        self.options.setEnabled(checked)
        self.changed.emit()

    def settings(self) -> SpellsSettings:
        return SpellsSettings(self.enabled.isChecked(), self.distribution.values(), self.player.isChecked(),
                              self.enemy.isChecked(), self.visual_chance.value() / 100, self.cross_school.isChecked(),
                              self.status_chance.value() / 100, self.write_summaries.isChecked())

    def apply(self, settings: SpellsSettings) -> None:
        widgets = (self.enabled, self.player, self.enemy, self.cross_school, self.write_summaries, self.visual_chance,
                   self.status_chance, self.distribution)
        for widget in widgets:
            widget.blockSignals(True)
        self.enabled.setChecked(settings.enabled)
        self.player.setChecked(settings.player)
        self.enemy.setChecked(settings.enemy)
        self.cross_school.setChecked(settings.cross_school_visuals)
        self.write_summaries.setChecked(settings.write_summaries)
        self.visual_chance.setValue(round(settings.visual_chance * 100))
        self.status_chance.setValue(round(settings.status_chance * 100))
        self.distribution.set_values(settings.tier_weights)
        for widget in widgets:
            widget.blockSignals(False)
        self.options.setEnabled(settings.enabled)

    def show_results(self, result: RunResult) -> None:
        self.results.setRowCount(len(result.spells))
        for row, spell in enumerate(result.spells):
            name = result.spell_names.get(spell.magic_id) or f"NPC spell {spell.magic_id}"
            donor = result.spell_names.get(spell.donor) or f"NPC spell {spell.donor}"
            casts = str(spell.casts) if spell.owner == "player" else "-"
            for col, text in enumerate((name, spell.owner, spell.tier.name.title(), casts, donor,
                                        f"{spell.power:.2f}")):
                self.results.setItem(row, col, QtWidgets.QTableWidgetItem(text))
        self.results.resizeColumnsToContents()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DS1 Parameter Randomizer")
        self.settings = QtCore.QSettings("ds1rand", "ds1rand")
        self._loading = False
        self._thread: QtCore.QThread | None = None

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.addLayout(self._build_top())

        self.tabs = QtWidgets.QTabWidget()
        self.rings_tab = RingsTab()
        self.rings_tab.changed.connect(self._settings_edited)
        self.tabs.addTab(self.rings_tab, "Rings")
        self.spells_tab = SpellsTab()
        self.spells_tab.changed.connect(self._settings_edited)
        self.tabs.addTab(self.spells_tab, "Spells")
        for name in ("Projectiles", "Enemy Behaviour"):
            placeholder = QtWidgets.QLabel(f"{name} randomization is not built yet (roadmap Phase 6).")
            placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.tabs.setTabEnabled(self.tabs.addTab(placeholder, name), False)
        self.install_view = QtWidgets.QPlainTextEdit(readOnly=True)
        self.install_view.setPlaceholderText("Validate the install to see what a run would build on.")
        self.tabs.addTab(self.install_view, "Install")
        layout.addWidget(self.tabs, stretch=3)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        self.validate_button = QtWidgets.QPushButton("Validate install")
        self.validate_button.clicked.connect(self._validate)
        self.randomize_button = QtWidgets.QPushButton("Randomize")
        self.randomize_button.setDefault(True)
        self.randomize_button.clicked.connect(self._randomize)
        buttons.addWidget(self.validate_button)
        buttons.addWidget(self.randomize_button)
        layout.addLayout(buttons)

        self.log = QtWidgets.QPlainTextEdit(readOnly=True)
        self.log.setMaximumBlockCount(2000)
        layout.addWidget(self.log, stretch=1)

        self.game_dir.setText(self.settings.value("game_dir", str(GameInstall.default().root)))
        last = self.settings.value("preset")
        self.apply_preset(Preset.from_json(last) if last else BUILTIN["Standard"])
        self.resize(900, 700)

    # Layout

    def _build_top(self) -> QtWidgets.QFormLayout:
        form = QtWidgets.QFormLayout()

        row = QtWidgets.QHBoxLayout()
        self.preset_combo = QtWidgets.QComboBox()
        self.preset_combo.addItems([*BUILTIN, CUSTOM])
        self.preset_combo.currentTextChanged.connect(self._preset_selected)
        row.addWidget(self.preset_combo, stretch=1)
        for text, slot in (("Import...", self._import_file), ("Export...", self._export_file),
                           ("Copy share string", self._copy_share), ("Paste share string", self._paste_share)):
            button = QtWidgets.QPushButton(text)
            button.clicked.connect(slot)
            row.addWidget(button)
        form.addRow("Preset", row)

        row = QtWidgets.QHBoxLayout()
        self.game_dir = QtWidgets.QLineEdit()
        browse = QtWidgets.QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        row.addWidget(self.game_dir, stretch=1)
        row.addWidget(browse)
        form.addRow("Game folder", row)

        row = QtWidgets.QHBoxLayout()
        self.seed = QtWidgets.QLineEdit()
        self.seed.setPlaceholderText("random")
        self.seed.setValidator(QtGui.QIntValidator(0, 2**31 - 1))
        self.seed.textChanged.connect(self._settings_edited)
        reroll = QtWidgets.QPushButton("New seed")
        reroll.clicked.connect(lambda: self.seed.setText(str(random.randrange(2**31))))
        row.addWidget(self.seed, stretch=1)
        row.addWidget(reroll)
        form.addRow("Seed", row)

        row = QtWidgets.QHBoxLayout()
        self.to_out = QtWidgets.QRadioButton(f"Output folder ({DEFAULT_OUT})")
        self.in_place = QtWidgets.QRadioButton("Write into the game folder")
        self.to_out.setChecked(True)
        row.addWidget(self.to_out)
        row.addWidget(self.in_place)
        row.addStretch()
        form.addRow("Output", row)
        return form

    # Presets

    def current_preset(self) -> Preset:
        seed = int(self.seed.text()) if self.seed.text() else None
        name = self.preset_combo.currentText()
        return Preset(name=name, seed=seed, rings=self.rings_tab.settings(), spells=self.spells_tab.settings())

    def apply_preset(self, preset: Preset) -> None:
        self._loading = True
        self.rings_tab.apply(preset.rings)
        self.spells_tab.apply(preset.spells)
        self.seed.setText("" if preset.seed is None else str(preset.seed))
        builtin = BUILTIN.get(preset.name)
        same = builtin is not None and _sections(builtin) == _sections(preset)
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentText(preset.name if same else CUSTOM)
        self.preset_combo.blockSignals(False)
        self._loading = False

    def _preset_selected(self, name: str) -> None:
        if name in BUILTIN:
            preset = Preset.from_dict(BUILTIN[name].to_dict())
            preset.seed = self.current_preset().seed
            self.apply_preset(preset)

    def _settings_edited(self) -> None:
        if self._loading:
            return
        name = self.preset_combo.currentText()
        if name in BUILTIN and _sections(BUILTIN[name]) != _sections(self.current_preset()):
            self.preset_combo.blockSignals(True)
            self.preset_combo.setCurrentText(CUSTOM)
            self.preset_combo.blockSignals(False)

    def _import_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Import preset", "", "Presets (*.json)")
        if path:
            self._load_preset(lambda: Preset.load(path))

    def _export_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export preset", "preset.json", "Presets (*.json)")
        if path:
            self.current_preset().save(path)
            self._log(f"Exported preset to {path}")

    def _copy_share(self) -> None:
        text = self.current_preset().to_share_string()
        QtWidgets.QApplication.clipboard().setText(text)
        self._log(f"Copied share string: {text}")

    def _paste_share(self) -> None:
        text = QtWidgets.QApplication.clipboard().text()
        self._load_preset(lambda: Preset.from_share_string(text))

    def _load_preset(self, load) -> None:
        try:
            preset = load()
        except Exception as error:  # bad file or string: tell the user
            QtWidgets.QMessageBox.warning(self, "Invalid preset", str(error))
            return
        self.apply_preset(preset)
        self._log(f"Loaded preset {preset.name!r}")

    # Running

    def _browse(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Dark Souls: Remastered folder", self.game_dir.text())
        if path:
            self.game_dir.setText(path)

    def _install(self) -> GameInstall | None:
        install = GameInstall(Path(self.game_dir.text()))
        missing = install.missing_files()
        if missing:
            QtWidgets.QMessageBox.warning(self, "Not a DSR folder", "Missing:\n" + "\n".join(map(str, missing)))
            return None
        self.settings.setValue("game_dir", str(install.root))
        return install

    def _validate(self) -> None:
        install = self._install()
        if install:
            self._start(lambda log: validate(install), self._show_install, "Validating")

    def _randomize(self) -> None:
        install = self._install()
        if install is None:
            return
        for tab, label in ((self.rings_tab, "Ring"), (self.spells_tab, "Spell")):
            if tab.enabled.isChecked() and not tab.distribution.is_valid():
                QtWidgets.QMessageBox.warning(self, "Invalid settings", f"{label} tier weights must not all be 0.")
                return
        preset = self.current_preset()
        self.settings.setValue("preset", preset.to_json())
        out_dir = None if self.in_place.isChecked() else DEFAULT_OUT
        self._start(lambda log: run(preset, install, out_dir, log), self._show_run, "Randomizing")

    def _start(self, job, on_done, label: str) -> None:
        self._log(f"{label}...")
        self.validate_button.setEnabled(False)
        self.randomize_button.setEnabled(False)
        self._thread = QtCore.QThread(self)
        self._worker = _Worker(job)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)
        self._worker.log.connect(self._log)
        self._worker.finished.connect(on_done)
        self._worker.failed.connect(self._failed)
        for signal in (self._worker.finished, self._worker.failed):
            signal.connect(self._thread.quit)
        self._thread.finished.connect(self._done)
        self._thread.start()

    def _done(self) -> None:
        self.validate_button.setEnabled(True)
        self.randomize_button.setEnabled(True)

    def _failed(self, message: str) -> None:
        self._log(message)
        QtWidgets.QMessageBox.critical(self, "ds1rand", message.strip().splitlines()[-1])

    def _show_install(self, result: RunResult) -> None:
        lines = [f"GameParam base: {result.gameparam_base}", f"Item text base: {result.text_base}", ""]
        lines += ["Changes by other mods (kept):"] + [f"  {c}" for c in result.foreign or ["none"]]
        lines += ["", "Conflicts with the previous ds1rand run:"] + [f"  {c}" for c in result.conflicts or ["none"]]
        self.install_view.setPlainText("\n".join(lines))
        self.tabs.setCurrentWidget(self.install_view)
        self._log("Validation done")

    def _show_run(self, result: RunResult) -> None:
        self.rings_tab.show_results(result)
        self.spells_tab.show_results(result)
        self.seed.setText(str(result.seed))
        self._log(f"Done (seed {result.seed}). Share string: {self.current_preset().to_share_string()}")

    def _log(self, text: str) -> None:
        self.log.appendPlainText(text)


def _sections(preset: Preset) -> tuple:
    """The feature settings of a preset (what decides whether it still matches a built-in)."""
    return preset.rings, preset.spells


def main() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()
