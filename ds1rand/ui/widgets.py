"""Reusable UI widgets."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class DistributionEditor(QtWidgets.QWidget):
    """Weights for a set of buckets (e.g. ring tiers), with named presets. Weights need not sum to 1; the share of each
    bucket is shown next to it."""

    changed = QtCore.Signal()

    def __init__(self, labels: list[str], presets: dict[str, tuple[float, ...]], parent=None):
        super().__init__(parent)
        self._presets = presets
        self._updating = False
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.preset_combo = QtWidgets.QComboBox()
        self.preset_combo.addItems([*presets, "Custom"])
        self.preset_combo.currentTextChanged.connect(self._preset_selected)
        layout.addWidget(self.preset_combo)

        grid = QtWidgets.QGridLayout()
        self.spins: list[QtWidgets.QDoubleSpinBox] = []
        self.shares: list[QtWidgets.QLabel] = []
        for row, label in enumerate(labels):
            spin = QtWidgets.QDoubleSpinBox()
            spin.setRange(0, 1000)
            spin.setDecimals(3)
            spin.setSingleStep(0.05)
            spin.valueChanged.connect(self._edited)
            share = QtWidgets.QLabel()
            share.setMinimumWidth(50)
            grid.addWidget(QtWidgets.QLabel(label), row, 0)
            grid.addWidget(spin, row, 1)
            grid.addWidget(share, row, 2)
            self.spins.append(spin)
            self.shares.append(share)
        layout.addLayout(grid)
        self.warning = QtWidgets.QLabel()
        self.warning.setStyleSheet("color: #c0392b")
        layout.addWidget(self.warning)
        self._preset_selected(self.preset_combo.currentText())

    def values(self) -> tuple[float, ...]:
        return tuple(spin.value() for spin in self.spins)

    def set_values(self, values) -> None:
        self._updating = True
        for spin, value in zip(self.spins, values):
            spin.setValue(float(value))
        self._updating = False
        match = next((name for name, preset in self._presets.items() if tuple(preset) == tuple(values)), "Custom")
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentText(match)
        self.preset_combo.blockSignals(False)
        self._refresh()

    def is_valid(self) -> bool:
        return sum(self.values()) > 0

    def _preset_selected(self, name: str) -> None:
        if name in self._presets:
            self.set_values(self._presets[name])
            self.changed.emit()

    def _edited(self) -> None:
        if self._updating:
            return
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentText("Custom")
        self.preset_combo.blockSignals(False)
        self._refresh()
        self.changed.emit()

    def _refresh(self) -> None:
        total = sum(self.values())
        for spin, share in zip(self.spins, self.shares):
            share.setText(f"{spin.value() / total:.1%}" if total else "-")
        self.warning.setText("" if total > 0 else "At least one weight must be above 0")
