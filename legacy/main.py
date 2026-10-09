
import os
import sys

from PySide6 import QtCore, QtWidgets, QtGui
from randomizer import Randomizer


class MyWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.presets = {
            "Easy": [0.65, 0.2, 0.1, 0.05],
            "Standard": [0.7, 0.2, 0.08, 0.02],
            "Hard": [0.85, 0.1, 0.04, 0.01],
            "Misery": [0.9, 0.075, 0.02, 0.005],
            "Custom": [0.7, 0.2, 0.08, 0.02],
        }

        main_layout = QtWidgets.QVBoxLayout(self)

        # Top: Game Directory selector
        dir_layout = QtWidgets.QHBoxLayout()
        dir_label = QtWidgets.QLabel("Game Directory")
        self.dir_edit = QtWidgets.QLineEdit()
        browse_btn = QtWidgets.QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_folder)
        dir_layout.addWidget(dir_label)
        dir_layout.addWidget(self.dir_edit)
        dir_layout.addWidget(browse_btn)
        main_layout.addLayout(dir_layout)

        # Seed entry
        seed_layout = QtWidgets.QHBoxLayout()
        seed_label = QtWidgets.QLabel("Seed")
        self.seed_edit = QtWidgets.QLineEdit()
        seed_layout.addWidget(seed_label)
        seed_layout.addWidget(self.seed_edit)
        main_layout.addLayout(seed_layout)

        # Middle: General and Rings groupboxes side-by-side
        mid_layout = QtWidgets.QHBoxLayout()

        # General group
        general_box = QtWidgets.QGroupBox("general")
        general_layout = QtWidgets.QVBoxLayout()
        self.chk_write_summary = QtWidgets.QCheckBox("Write Item Summaries")
        self.chk_append_quality = QtWidgets.QCheckBox("Append Quality To Item Names")
        general_layout.addWidget(self.chk_write_summary)
        general_layout.addWidget(self.chk_append_quality)
        general_layout.addStretch()
        general_box.setLayout(general_layout)
        mid_layout.addWidget(general_box, stretch=1)

        # Rings group
        rings_box = QtWidgets.QGroupBox("Rings")
        rings_layout = QtWidgets.QVBoxLayout()

        self.chk_randomize_rings = QtWidgets.QCheckBox("Randomize Rings")
        self.chk_randomize_rings.setChecked(True)
        self.chk_randomize_rings.toggled.connect(self.on_randomize_toggled)
        rings_layout.addWidget(self.chk_randomize_rings)

        # Ring Distribution Settings group
        self.ring_dist_box = QtWidgets.QGroupBox("Ring Distribution Settings")
        rd_layout = QtWidgets.QVBoxLayout()

        self.combo_dist = QtWidgets.QComboBox()
        self.combo_dist.addItems(["Easy", "Standard", "Hard", "Misery", "Custom"])
        self.combo_dist.setCurrentText("Standard")
        self.combo_dist.currentTextChanged.connect(self.on_preset_changed)
        rd_layout.addWidget(self.combo_dist)

        # Four label+entry pairs
        grid = QtWidgets.QGridLayout()
        labels = ["Standard", "Uncommon", "Rare", "Legendary"]
        self.ring_edits = []
        for i, name in enumerate(labels):
            lbl = QtWidgets.QLabel(name)
            edit = QtWidgets.QLineEdit()
            edit.setFixedWidth(100)
            edit.setAlignment(QtCore.Qt.AlignRight)
            edit.textChanged.connect(self.validate_distribution)
            grid.addWidget(lbl, i, 0)
            grid.addWidget(edit, i, 1)
            self.ring_edits.append(edit)

        rd_layout.addLayout(grid)

        # Warning label
        self.warn_label = QtWidgets.QLabel("")
        self.warn_label.setStyleSheet("color: red")
        rd_layout.addWidget(self.warn_label)

        self.ring_dist_box.setLayout(rd_layout)
        rings_layout.addWidget(self.ring_dist_box)

        rings_box.setLayout(rings_layout)
        mid_layout.addWidget(rings_box, stretch=2)

        main_layout.addLayout(mid_layout)

        # Bottom: Randomize button
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        randomize_btn = QtWidgets.QPushButton("Randomize")
        randomize_btn.clicked.connect(self.on_randomize_clicked)
        btn_layout.addWidget(randomize_btn)
        main_layout.addLayout(btn_layout)

        # Initialize values
        self.on_preset_changed(self.combo_dist.currentText())
        self.on_randomize_toggled(self.chk_randomize_rings.isChecked())

    def browse_folder(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Game Directory")
        if path:
            self.dir_edit.setText(path)

    def on_randomize_toggled(self, checked: bool):
        self.ring_dist_box.setEnabled(checked)

    def on_preset_changed(self, text: str):
        preset = self.presets.get(text, self.presets["Standard"]) if text else self.presets["Standard"]
        for edit, val in zip(self.ring_edits, preset):
            edit.setText(f"{val:.6g}")

        is_custom = (text == "Custom")
        for edit in self.ring_edits:
            edit.setReadOnly(not is_custom)
            if not is_custom:
                edit.setStyleSheet("background-color: #f0f0f0")
            else:
                edit.setStyleSheet("")

        self.validate_distribution()

    def validate_distribution(self):
        total = 0.0
        for edit in self.ring_edits:
            text = edit.text().strip()
            if not text:
                val = 0.0
            else:
                try:
                    val = float(text)
                except ValueError:
                    val = None
            if val is None:
                self.warn_label.setText("Invalid number in distribution")
                return False
            total += val

        if abs(total - 1.0) > 1e-6:
            self.warn_label.setText("Warning: distribution values must add up to 1.0")
            return False
        else:
            self.warn_label.setText("")
            return True

    def on_randomize_clicked(self):
        if not self.validate_distribution():
            QtWidgets.QMessageBox.warning(self, "Invalid Distribution", "Please fix ring distribution to sum to 1.0 before randomizing.")
            return

        # Check that dir_edit is a valid directory
        game_dir = self.dir_edit.text().strip()
        if not os.path.isdir(game_dir):
            QtWidgets.QMessageBox.warning(self, "Invalid Directory", "Please select a valid game directory before randomizing.")
            return
        # Check that it contains a param/GameParam/GameParam.parambnd.dcx file
        param_path = os.path.join(game_dir, "param", "GameParam", "GameParam.parambnd.dcx")
        if not os.path.isfile(param_path):
            QtWidgets.QMessageBox.warning(self, "File Not Found", f"Could not find GameParam.parambnd.dcx at expected location:\n{param_path}\nPlease select a valid game directory.")
            return
        # Check that it contains a msg/ENGLISH/item.msgbnd.dcx file
        msgbnd_path = os.path.join(game_dir, "msg", "ENGLISH", "item.msgbnd.dcx")
        if not os.path.isfile(param_path):
            QtWidgets.QMessageBox.warning(self, "File Not Found", f"Could not find item.msgbnd.dcx at expected location:\n{msgbnd_path}\nPlease select a valid game directory.")
            return
        ring_distribution = [float(ring_edit.text().strip()) for ring_edit in self.ring_edits]
        randomizer = Randomizer(self.dir_edit.text() + "\\param\\GameParam\\GameParam.parambnd.dcx", self.dir_edit.text() + "\\msg\\ENGLISH\\item.msgbnd.dcx", ring_distribution=ring_distribution, write_item_summary=self.chk_write_summary.isChecked())
        randomizer.randomize()
        # Placeholder randomize action
        QtWidgets.QMessageBox.information(self, "Randomize", "Randomization complete.")


if __name__ == "__main__":
    app = QtWidgets.QApplication([])

    widget = MyWidget()
    widget.resize(800, 400)
    widget.show()

    sys.exit(app.exec())