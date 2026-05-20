from __future__ import annotations

from PySide6.QtWidgets import QTableView, QVBoxLayout, QWidget

from detector_scenario_tool.ui.models.scenario_table_model import ScenarioTableModel


class ScenarioTablePanel(QWidget):
    def __init__(self, model: ScenarioTableModel) -> None:
        super().__init__()
        self.table = QTableView(self)
        self.table.setModel(model)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 48)
        self.table.setColumnWidth(1, 42)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 260)
        self.table.setColumnWidth(4, 220)
        self.table.setColumnWidth(5, 100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)
