"""Audit tab: a read-only browser of the reference graph and catalogue of the last Validate / Randomize.

Top: coverage per param (rows, rows used by a feature, rows shared by several features, rows per feature, unresolved
references, rows this run changed or added). Bottom: pick a param, filter rows by ID or name, and see a row's usage,
subtype, references in both directions (with source and confidence) and its values in vanilla, the base (after other
mods) and this run.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ds1rand.catalogue.inspect import coverage, describe_row, row_name
from ds1rand.catalogue.usage import FEATURES
from ds1rand.session import Session

MAX_LISTED = 1000


class AuditTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.session: Session | None = None
        layout = QtWidgets.QVBoxLayout(self)
        self.status = QtWidgets.QLabel("Validate or Randomize to load the reference graph of the install.")
        layout.addWidget(self.status)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.coverage = QtWidgets.QTableWidget(0, 6 + len(FEATURES))
        self.coverage.setHorizontalHeaderLabels(["Param", "Rows", "Used", "Shared", *FEATURES, "Unresolved refs",
                                                 "Changed this run"])
        self.coverage.verticalHeader().setVisible(False)
        self.coverage.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.coverage.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.coverage.cellDoubleClicked.connect(lambda row, _col: self.param.setCurrentText(
            self.coverage.item(row, 0).text()))
        splitter.addWidget(self.coverage)

        browser = QtWidgets.QWidget()
        browser_layout = QtWidgets.QHBoxLayout(browser)
        browser_layout.setContentsMargins(0, 0, 0, 0)
        left = QtWidgets.QVBoxLayout()
        self.param = QtWidgets.QComboBox()
        self.param.currentTextChanged.connect(self._fill_rows)
        self.filter = QtWidgets.QLineEdit(placeholderText="Filter by ID or name")
        self.filter.textChanged.connect(self._fill_rows)
        self.rows = QtWidgets.QListWidget()
        self.rows.currentItemChanged.connect(self._show_row)
        for widget in (self.param, self.filter, self.rows):
            left.addWidget(widget)
        browser_layout.addLayout(left, 1)
        self.details = QtWidgets.QPlainTextEdit(readOnly=True)
        self.details.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont))
        browser_layout.addWidget(self.details, 3)
        splitter.addWidget(browser)
        layout.addWidget(splitter, stretch=1)
        self.setEnabled(True)

    def set_session(self, session: Session | None) -> None:
        if session is None:
            return
        self.session = session
        changes = session.store.changes()
        self.status.setText(f"{session.install.root}: {len(session.graph.edges)} references, "
                            f"{len(session.graph.unresolved)} unresolved; "
                            f"{sum(len(v) for v in changes.values())} rows changed or added by this run.")
        table = coverage(session)
        self.coverage.setRowCount(len(table))
        for row, c in enumerate(table):
            cells = [c.param, c.rows, c.used, c.shared, *(c.per_feature[f] for f in FEATURES), c.unresolved, c.changed]
            for col, value in enumerate(cells):
                self.coverage.setItem(row, col, QtWidgets.QTableWidgetItem(str(value)))
        self.coverage.resizeColumnsToContents()
        current = self.param.currentText()
        self.param.blockSignals(True)
        self.param.clear()
        self.param.addItems(sorted(session.base.params))
        self.param.blockSignals(False)
        self.param.setCurrentText(current if current in session.base.params else "Bullet")
        self._fill_rows()

    def _fill_rows(self) -> None:
        self.rows.clear()
        if self.session is None or not self.param.currentText():
            return
        param = self.param.currentText()
        ids = sorted(set(self.session.base.params[param].rows) | set(self.session.store.changes().get(param, {})))
        needle = self.filter.text().strip().lower()
        listed = 0
        for row_id in ids:
            name = row_name(self.session, param, row_id)
            if needle and needle not in str(row_id) and needle not in name.lower():
                continue
            item = QtWidgets.QListWidgetItem(f"{row_id}  {name}".rstrip())
            item.setData(QtCore.Qt.ItemDataRole.UserRole, row_id)
            self.rows.addItem(item)
            listed += 1
            if listed >= MAX_LISTED:
                self.rows.addItem(f"... (first {MAX_LISTED}; filter to narrow)")
                break

    def _show_row(self, item: QtWidgets.QListWidgetItem | None) -> None:
        if item is None or self.session is None or item.data(QtCore.Qt.ItemDataRole.UserRole) is None:
            return
        report = describe_row(self.session, self.param.currentText(), item.data(QtCore.Qt.ItemDataRole.UserRole))
        self.details.setPlainText(report.text())
