from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from detector_scenario_tool.domain.log_roles import normalize_log_source
from detector_scenario_tool.domain.logs import LogRecord
from detector_scenario_tool.i18n import tr
from detector_scenario_tool.protocol.catalog import ProtocolCatalog
from detector_scenario_tool.ui.delegates.row_outline_delegate import RowOutlineDelegate
from detector_scenario_tool.ui.models.log_table_model import LogTableModel


class LogPanel(QWidget):
    import_requested = Signal()
    clear_requested = Signal()
    start_live_requested = Signal(str, str, int)
    stop_live_requested = Signal()
    pause_live_requested = Signal()
    resume_live_requested = Signal()
    save_session_toggled = Signal(bool, str)

    def __init__(self, catalog: ProtocolCatalog) -> None:
        super().__init__()

        self.setStyleSheet("""
            QWidget {
                background-color: #121212;
                color: #e6e6e6;
            }
            QTableView {
                background-color: #121212;
                color: #e6e6e6;
                gridline-color: #444444;
                selection-background-color: transparent;
                selection-color: white;
            }
            QHeaderView::section {
                background-color: #1d1d1d;
                color: #e6e6e6;
                border: 1px solid #333333;
                padding: 4px;
            }
            QPushButton, QComboBox, QLineEdit {
                background-color: #2a2a2a;
                color: #e6e6e6;
                border: 1px solid #555555;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #353535;
            }
            QLabel {
                color: #e6e6e6;
            }
            QCheckBox {
                color: #e6e6e6;
            }
        """)

        self.model = LogTableModel(catalog)

        self._all_records: list[LogRecord] = []
        self._matched_rows_all: set[int] = set()
        self._problem_rows_all: set[int] = set()
        self._filtered_to_original: list[int] = []
        self._original_to_filtered: dict[int, int] = {}

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.table.verticalHeader().setVisible(False)
        self.table.setItemDelegate(RowOutlineDelegate(self.table))

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)

        self.table.setColumnWidth(3, 260)
        self.table.setColumnWidth(5, 300)

        self.import_button = QPushButton()
        self.clear_button = QPushButton()

        self.port1_label = QLabel()
        self.port2_label = QLabel()
        self.baud_label = QLabel()

        self.port1_edit = QLineEdit("/dev/ttyACM0")
        self.port2_edit = QLineEdit("/dev/ttyACM1")
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["115200", "230400", "460800", "921600"])
        self.baud_combo.setCurrentText("115200")

        self.start_live_button = QPushButton()
        self.stop_live_button = QPushButton()
        self.pause_live_button = QPushButton()
        self.resume_live_button = QPushButton()

        self.auto_scroll_checkbox = QCheckBox()
        self.auto_scroll_checkbox.setChecked(True)

        self.save_session_checkbox = QCheckBox()
        self.save_session_path_edit = QLineEdit()
        self.save_session_browse_button = QPushButton()

        self.dir_filter = QComboBox()
        self.category_filter = QComboBox()
        self.source_filter = QComboBox()

        self.problems_only_checkbox = QCheckBox()
        self.reset_filters_button = QPushButton()

        self.live_status_label = QLabel()
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)

        top_buttons = QHBoxLayout()
        top_buttons.setContentsMargins(8, 8, 8, 6)
        top_buttons.setSpacing(8)
        top_buttons.addWidget(self.import_button)
        top_buttons.addWidget(self.clear_button)
        top_buttons.addStretch(1)

        live_controls = QHBoxLayout()
        live_controls.setContentsMargins(8, 0, 8, 6)
        live_controls.setSpacing(8)
        live_controls.addWidget(self.port1_label)
        live_controls.addWidget(self.port1_edit)
        live_controls.addWidget(self.port2_label)
        live_controls.addWidget(self.port2_edit)
        live_controls.addWidget(self.baud_label)
        live_controls.addWidget(self.baud_combo)
        live_controls.addWidget(self.start_live_button)
        live_controls.addWidget(self.stop_live_button)
        live_controls.addWidget(self.pause_live_button)
        live_controls.addWidget(self.resume_live_button)
        live_controls.addWidget(self.auto_scroll_checkbox)
        live_controls.addStretch(1)

        save_controls = QHBoxLayout()
        save_controls.setContentsMargins(8, 0, 8, 6)
        save_controls.setSpacing(8)
        save_controls.addWidget(self.save_session_checkbox)
        save_controls.addWidget(self.save_session_path_edit)
        save_controls.addWidget(self.save_session_browse_button)

        filters = QHBoxLayout()
        filters.setContentsMargins(8, 0, 8, 6)
        filters.setSpacing(8)
        filters.addWidget(self.dir_filter)
        filters.addWidget(self.category_filter)
        filters.addWidget(self.source_filter)
        filters.addWidget(self.problems_only_checkbox)
        filters.addWidget(self.reset_filters_button)
        filters.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(top_buttons)
        layout.addLayout(live_controls)
        layout.addLayout(save_controls)
        layout.addWidget(self.live_status_label)
        layout.addLayout(filters)
        layout.addWidget(self.table)
        layout.addWidget(self.summary_label)

        self.import_button.clicked.connect(self.import_requested.emit)
        self.clear_button.clicked.connect(self.clear_requested.emit)
        self.start_live_button.clicked.connect(self._emit_start_live)
        self.stop_live_button.clicked.connect(self.stop_live_requested.emit)
        self.pause_live_button.clicked.connect(self.pause_live_requested.emit)
        self.resume_live_button.clicked.connect(self.resume_live_requested.emit)

        self.save_session_browse_button.clicked.connect(self._browse_session_file)
        self.save_session_checkbox.toggled.connect(self._emit_save_session_toggled)

        self.dir_filter.currentIndexChanged.connect(self._apply_filters)
        self.category_filter.currentIndexChanged.connect(self._apply_filters)
        self.source_filter.currentIndexChanged.connect(self._apply_filters)
        self.problems_only_checkbox.toggled.connect(self._apply_filters)
        self.reset_filters_button.clicked.connect(self._reset_filters)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.import_button.setText(tr("logs.import"))
        self.clear_button.setText(tr("logs.clear"))

        self.port1_label.setText(tr("logs.port1"))
        self.port2_label.setText(tr("logs.port2"))
        self.baud_label.setText(tr("logs.baud"))

        self.start_live_button.setText(tr("logs.start_live"))
        self.stop_live_button.setText(tr("logs.stop_live"))
        self.pause_live_button.setText(tr("logs.pause"))
        self.resume_live_button.setText(tr("logs.resume"))

        self.auto_scroll_checkbox.setText(tr("logs.auto_scroll"))
        self.save_session_checkbox.setText(tr("logs.save_session"))
        self.save_session_path_edit.setPlaceholderText(tr("logs.save_session_path_placeholder"))
        self.save_session_browse_button.setText(tr("logs.browse"))

        if not self.live_status_label.text():
            self.live_status_label.setText(tr("logs.live_stopped"))
        if not self.summary_label.text():
            self.summary_label.setText(tr("logs.no_logs_loaded"))

        dir_code = self.dir_filter.currentData()
        cat_code = self.category_filter.currentData()
        src_text = self.source_filter.currentText()
        problems_only = self.problems_only_checkbox.isChecked()

        self.dir_filter.blockSignals(True)
        self.dir_filter.clear()
        self.dir_filter.addItem(tr("logs.filter.dir.all"), "all")
        self.dir_filter.addItem(tr("logs.filter.dir.tx"), "tx")
        self.dir_filter.addItem(tr("logs.filter.dir.rx"), "rx")
        idx = self.dir_filter.findData(dir_code if dir_code is not None else "all")
        self.dir_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.dir_filter.blockSignals(False)

        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem(tr("logs.filter.category.all"), "all")
        self.category_filter.addItem("KU", "KU")
        self.category_filter.addItem("KT", "KT")
        self.category_filter.addItem("TS", "TS")
        idx = self.category_filter.findData(cat_code if cat_code is not None else "all")
        self.category_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.category_filter.blockSignals(False)

        self._rebuild_source_filter(selected_text=src_text)

        self.problems_only_checkbox.blockSignals(True)
        self.problems_only_checkbox.setText(tr("logs.filter.problems_only"))
        self.problems_only_checkbox.setChecked(problems_only)
        self.problems_only_checkbox.blockSignals(False)

        self.reset_filters_button.setText(tr("logs.filter.reset"))

    def set_records(self, records: list[LogRecord]) -> None:
        self._all_records = list(records)
        self._rebuild_source_filter()
        self._apply_filters()

    def set_matched_rows(self, matched_rows: set[int]) -> None:
        self._matched_rows_all = set(matched_rows)
        self._apply_filters()

    def set_problem_rows(self, problem_rows: set[int]) -> None:
        self._problem_rows_all = set(problem_rows)
        self._apply_filters()

    def set_summary_text(self, text: str) -> None:
        self.summary_label.setText(text)

    def set_row_tooltips(self, row_tooltips: dict[int, str]) -> None:
        filtered_tooltips = {
            self._original_to_filtered[i]: text
            for i, text in row_tooltips.items()
            if i in self._original_to_filtered
        }
        self.model.set_row_tooltips(filtered_tooltips)

    def set_live_status_text(self, text: str) -> None:
        self.live_status_label.setText(text)

    def is_auto_scroll_enabled(self) -> bool:
        return self.auto_scroll_checkbox.isChecked()

    def filtered_row_for_original(self, original_row: int) -> int | None:
        return self._original_to_filtered.get(original_row)

    def original_row_for_filtered(self, filtered_row: int) -> int | None:
        if 0 <= filtered_row < len(self._filtered_to_original):
            return self._filtered_to_original[filtered_row]
        return None

    def original_selected_row(self) -> int | None:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return None
        return self.original_row_for_filtered(indexes[0].row())

    def select_original_row(self, original_row: int | None) -> None:
        if original_row is None:
            self.table.clearSelection()
            return

        filtered_row = self.filtered_row_for_original(original_row)
        if filtered_row is None:
            self.table.clearSelection()
            return

        self.table.selectRow(filtered_row)
        self.table.scrollTo(self.model.index(filtered_row, 0))

    def _emit_start_live(self) -> None:
        port1 = self.port1_edit.text().strip()
        port2 = self.port2_edit.text().strip()
        baud = int(self.baud_combo.currentText())
        self.start_live_requested.emit(port1, port2, baud)

    def _browse_session_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("logs.save_session"),
            "",
            "Text files (*.log *.txt);;All files (*)",
        )
        if path:
            self.save_session_path_edit.setText(path)
            if self.save_session_checkbox.isChecked():
                self._emit_save_session_toggled(True)

    def _emit_save_session_toggled(self, checked: bool) -> None:
        self.save_session_toggled.emit(checked, self.save_session_path_edit.text().strip())

    def _reset_filters(self) -> None:
        self.dir_filter.setCurrentIndex(0)
        self.category_filter.setCurrentIndex(0)
        self.source_filter.setCurrentIndex(0)
        self.problems_only_checkbox.setChecked(False)

    def _rebuild_source_filter(self, selected_text: str | None = None) -> None:
        current = selected_text if selected_text is not None else self.source_filter.currentText()

        sources = sorted(
            {normalize_log_source(rec.source) for rec in self._all_records if normalize_log_source(rec.source)})
        self.source_filter.blockSignals(True)
        self.source_filter.clear()
        self.source_filter.addItem(tr("logs.filter.source.all"))
        for source in sources:
            self.source_filter.addItem(source)

        index = self.source_filter.findText(current)
        self.source_filter.setCurrentIndex(index if index >= 0 else 0)
        self.source_filter.blockSignals(False)

    def _apply_filters(self) -> None:
        dir_value = self.dir_filter.currentData()
        category_value = self.category_filter.currentData()
        source_value = self.source_filter.currentText()
        problems_only = self.problems_only_checkbox.isChecked()

        filtered_records: list[LogRecord] = []
        filtered_to_original: list[int] = []

        for i, record in enumerate(self._all_records):
            if dir_value == "tx" and record.direction != "tx":
                continue
            if dir_value == "rx" and record.direction != "rx":
                continue

            if category_value not in (None, "all") and record.category != category_value:
                continue

            record_source = normalize_log_source(record.source)
            if source_value != tr("logs.filter.source.all") and record_source != source_value:
                continue

            if problems_only and i not in self._problem_rows_all and i in self._matched_rows_all:
                continue

            filtered_records.append(record)
            filtered_to_original.append(i)

        self._filtered_to_original = filtered_to_original
        self._original_to_filtered = {orig: filt for filt, orig in enumerate(filtered_to_original)}

        filtered_matched_rows = {
            self._original_to_filtered[i]
            for i in self._matched_rows_all
            if i in self._original_to_filtered
        }

        filtered_problem_rows = {
            self._original_to_filtered[i]
            for i in self._problem_rows_all
            if i in self._original_to_filtered
        }

        self.model.set_items(filtered_records)
        self.model.set_matched_rows(filtered_matched_rows)
        self.model.set_problem_rows(filtered_problem_rows)
        self.table.resizeRowsToContents()
