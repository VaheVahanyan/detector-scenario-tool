from __future__ import annotations

import uuid
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from detector_scenario_tool.codegen import save_generated_scenario_files
from detector_scenario_tool.domain.log_roles import normalize_log_source
from detector_scenario_tool.domain.logs import LogRecord
from detector_scenario_tool.domain.scenario import (
    AckPolicy,
    MessageRef,
    RetryPolicy,
    ScenarioDocument,
    ScenarioMetadata,
    SendMessageStep,
    StepKind,
    ValidationProfile,
    WaitForTsStep,
    WaitTimeStep,
)
from detector_scenario_tool.i18n import get_language, set_language, tr
from detector_scenario_tool.protocol.catalog import ProtocolCatalog
from detector_scenario_tool.protocol.expected_responses import get_expected_responses
from detector_scenario_tool.services.serial_log_controller import SerialLogController
from detector_scenario_tool.storage.log_io import load_log_records, format_log_record_line
from detector_scenario_tool.storage.packed_export import save_packed_scenario_export
from detector_scenario_tool.storage.scenario_io import load_scenario, save_scenario
from detector_scenario_tool.ui.delegates.wrap_text_delegate import WrapTextDelegate
from detector_scenario_tool.ui.models.scenario_table_model import ScenarioTableModel
from detector_scenario_tool.ui.models.warnings_table_model import WarningsTableModel
from detector_scenario_tool.ui.panels.inspector_panel import InspectorPanel
from detector_scenario_tool.ui.panels.log_panel import LogPanel
from detector_scenario_tool.ui.panels.timeline_panel import TimelinePanel
from detector_scenario_tool.validation.analyzer import analyze_scenario


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Detector Scenario Tool")
        self.resize(1500, 920)

        self.catalog = ProtocolCatalog()
        self.current_path: Path | None = None
        self.log_records: list[LogRecord] = []

        self._step_to_log_row: dict[int, int] = {}
        self._log_to_step_row: dict[int, int] = {}
        self._step_execution_details: dict[int, str] = {}
        self._log_execution_details: dict[int, str] = {}
        self._selection_sync_in_progress = False

        self._serial_controllers: list[SerialLogController] = []
        self._live_refresh_pending = False
        self._live_session_save_enabled = False
        self._live_session_save_path = ""
        self._live_session_file = None

        self.document = ScenarioDocument(
            schema_version=1,
            metadata=ScenarioMetadata(name="Untitled scenario"),
            validation=ValidationProfile(),
            steps=[],
        )

        self.table_model = ScenarioTableModel(self.document)
        self.table_view = QTableView()
        self.table_view.setModel(self.table_model)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table_view.setWordWrap(True)
        self.table_view.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.verticalHeader().setDefaultSectionSize(34)
        self.table_view.horizontalHeader().setStretchLastSection(False)
        self.table_view.setItemDelegate(WrapTextDelegate(self.table_view))
        self.table_view.setStyleSheet("""
            QTableView {
                gridline-color: #444444;
                selection-background-color: transparent;
                selection-color: white;
            }
        """)
        self.table_view.viewport().installEventFilter(self)

        self.add_ku_button = QPushButton(tr("button.add_ku"))
        self.add_kt_button = QPushButton(tr("button.add_kt"))
        self.add_wait_button = QPushButton(tr("button.add_wait"))
        self.add_wait_ts_button = QPushButton(tr("button.add_wait_ts"))
        self.add_expected_response_button = QPushButton(tr("button.add_expected_response"))

        self.timeline_panel = TimelinePanel()

        self.inspector_panel = InspectorPanel(self.catalog)
        self.inspector_panel.setMinimumWidth(320)

        self.warnings_model = WarningsTableModel()
        self.warnings_view = QTableView()
        self.warnings_view.setModel(self.warnings_model)
        self.warnings_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.warnings_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.warnings_view.setWordWrap(True)
        self.warnings_view.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.warnings_view.verticalHeader().setVisible(False)
        self.warnings_view.verticalHeader().setDefaultSectionSize(30)
        self.warnings_view.setItemDelegate(WrapTextDelegate(self.warnings_view))
        self.warnings_view.setStyleSheet("""
            QTableView {
                gridline-color: #444444;
                selection-background-color: transparent;
                selection-color: white;
            }
        """)
        self.warnings_view.viewport().installEventFilter(self)

        self.log_panel = LogPanel(self.catalog)

        self._build_actions()
        self._build_menus()
        self._build_layout()
        self._configure_table_columns()
        self._configure_warnings_columns()
        self._connect_signals()
        self.retranslate_ui()
        self._refresh_all_views()
        QTimer.singleShot(0, self._fill_table_width)
        QTimer.singleShot(0, self._fill_warnings_width)

    def _build_actions(self) -> None:
        self.new_action = QAction(tr("action.new"), self)
        self.open_action = QAction(tr("action.open"), self)
        self.save_action = QAction(tr("action.save"), self)
        self.save_as_action = QAction(tr("action.save_as"), self)
        self.export_packed_json_action = QAction(tr("action.export_packed_json"), self)
        self.export_generated_c_action = QAction(tr("action.export_generated_c"), self)
        self.import_logs_action = QAction(tr("action.import_logs"), self)

        self.add_ku_action = QAction(tr("action.add_ku"), self)
        self.add_kt_action = QAction(tr("action.add_kt"), self)
        self.add_wait_action = QAction(tr("action.add_wait"), self)
        self.add_wait_ts_action = QAction(tr("action.add_wait_ts"), self)
        self.add_expected_response_action = QAction(tr("action.add_expected_response"), self)

        self.delete_step_action = QAction(tr("action.delete_step"), self)
        self.delete_step_action.setShortcut(QKeySequence(Qt.Key.Key_Delete))

        self.move_step_up_action = QAction(tr("action.move_step_up"), self)
        self.move_step_up_action.setShortcut(QKeySequence("Ctrl+Up"))

        self.move_step_down_action = QAction(tr("action.move_step_down"), self)
        self.move_step_down_action.setShortcut(QKeySequence("Ctrl+Down"))

        self.duplicate_step_action = QAction(tr("action.duplicate_step"), self)
        self.duplicate_step_action.setShortcut(QKeySequence("Ctrl+D"))

        self.move_step_to_top_action = QAction(tr("action.move_step_to_top"), self)
        self.move_step_to_top_action.setShortcut(QKeySequence("Ctrl+Shift+Up"))

        self.move_step_to_bottom_action = QAction(tr("action.move_step_to_bottom"), self)
        self.move_step_to_bottom_action.setShortcut(QKeySequence("Ctrl+Shift+Down"))

        self.language_ru_action = QAction(tr("language.ru"), self)
        self.language_ru_action.setCheckable(True)

        self.language_en_action = QAction(tr("language.en"), self)
        self.language_en_action.setCheckable(True)

    def _build_menus(self) -> None:
        self.file_menu = self.menuBar().addMenu(tr("menu.file"))
        self.file_menu.addAction(self.new_action)
        self.file_menu.addAction(self.open_action)
        self.file_menu.addAction(self.save_action)
        self.file_menu.addAction(self.save_as_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.export_packed_json_action)
        self.file_menu.addAction(self.export_generated_c_action)
        self.file_menu.addAction(self.import_logs_action)

        self.edit_menu = self.menuBar().addMenu(tr("menu.edit"))
        self.edit_menu.addAction(self.add_ku_action)
        self.edit_menu.addAction(self.add_kt_action)
        self.edit_menu.addAction(self.add_wait_action)
        self.edit_menu.addAction(self.add_wait_ts_action)
        self.edit_menu.addAction(self.add_expected_response_action)
        self.edit_menu.addSeparator()
        self.edit_menu.addAction(self.duplicate_step_action)
        self.edit_menu.addAction(self.delete_step_action)
        self.edit_menu.addSeparator()
        self.edit_menu.addAction(self.move_step_up_action)
        self.edit_menu.addAction(self.move_step_down_action)
        self.edit_menu.addAction(self.move_step_to_top_action)
        self.edit_menu.addAction(self.move_step_to_bottom_action)

        self.language_menu = self.menuBar().addMenu(tr("menu.language"))
        self.language_menu.addAction(self.language_ru_action)
        self.language_menu.addAction(self.language_en_action)

    def _build_layout(self) -> None:
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(8, 8, 8, 6)
        toolbar_layout.setSpacing(8)
        toolbar_layout.addWidget(self.add_ku_button)
        toolbar_layout.addWidget(self.add_kt_button)
        toolbar_layout.addWidget(self.add_wait_button)
        toolbar_layout.addWidget(self.add_wait_ts_button)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self.add_expected_response_button)

        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)
        table_layout.addLayout(toolbar_layout)
        table_layout.addWidget(self.table_view)

        self.bottom_tabs = QTabWidget()
        self.bottom_tabs.addTab(self.log_panel, tr("tab.logs"))
        self.bottom_tabs.addTab(self.warnings_view, tr("tab.warnings"))

        left_bottom_splitter = QSplitter(Qt.Orientation.Vertical)
        left_bottom_splitter.addWidget(table_container)
        left_bottom_splitter.addWidget(self.bottom_tabs)
        left_bottom_splitter.setStretchFactor(0, 3)
        left_bottom_splitter.setStretchFactor(1, 2)

        inspector_scroll = QScrollArea()
        inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        inspector_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        inspector_scroll.setWidget(self.inspector_panel)

        lower_splitter = QSplitter(Qt.Orientation.Horizontal)
        lower_splitter.addWidget(left_bottom_splitter)
        lower_splitter.addWidget(inspector_scroll)
        lower_splitter.setStretchFactor(0, 3)
        lower_splitter.setStretchFactor(1, 2)

        self.timeline_panel.setFixedHeight(248)

        main_container = QWidget()
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.timeline_panel)
        main_layout.addWidget(lower_splitter, 1)

        lower_splitter.setSizes([980, 420])
        left_bottom_splitter.setSizes([160, 400])

        self.setCentralWidget(main_container)

    def _configure_table_columns(self) -> None:
        header = self.table_view.horizontalHeader()

        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)

        self.table_view.setColumnWidth(2, 120)
        self.table_view.setColumnWidth(4, 110)
        self.table_view.setColumnWidth(5, 240)

        self._fill_table_width()

    def _fill_table_width(self) -> None:
        viewport_width = self.table_view.viewport().width()
        if viewport_width <= 0:
            return

        fixed_width = (
                self.table_view.columnWidth(0)
                + self.table_view.columnWidth(1)
                + self.table_view.columnWidth(2)
                + self.table_view.columnWidth(4)
                + self.table_view.columnWidth(5)
        )

        remaining = viewport_width - fixed_width - 12
        self.table_view.setColumnWidth(3, max(260, remaining))

    def _configure_warnings_columns(self) -> None:
        header = self.warnings_view.horizontalHeader()

        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)

        self.warnings_view.setColumnWidth(0, 90)
        self.warnings_view.setColumnWidth(1, 70)
        self.warnings_view.setColumnWidth(2, 130)

        self._fill_warnings_width()

    def _fill_warnings_width(self) -> None:
        viewport_width = self.warnings_view.viewport().width()
        if viewport_width <= 0:
            return

        fixed_width = (
                self.warnings_view.columnWidth(0)
                + self.warnings_view.columnWidth(1)
                + self.warnings_view.columnWidth(2)
        )

        remaining = viewport_width - fixed_width - 12
        self.warnings_view.setColumnWidth(3, max(260, remaining))

    def _refresh_table_row_heights(self) -> None:
        self.table_view.resizeRowsToContents()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fill_table_width()
        self._fill_warnings_width()

    def closeEvent(self, event) -> None:
        self._stop_live_logs()
        self._close_live_session_file()
        super().closeEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Resize:
            if obj is self.table_view.viewport():
                QTimer.singleShot(0, self._fill_table_width)
            elif obj is self.warnings_view.viewport():
                QTimer.singleShot(0, self._fill_warnings_width)
        return super().eventFilter(obj, event)

    def _connect_signals(self) -> None:
        self.new_action.triggered.connect(self._new_document)
        self.open_action.triggered.connect(self._open_document)
        self.save_action.triggered.connect(self._save_document)
        self.save_as_action.triggered.connect(self._save_document_as)
        self.export_packed_json_action.triggered.connect(self._export_packed_json)
        self.export_generated_c_action.triggered.connect(self._export_generated_c)
        self.import_logs_action.triggered.connect(self._import_logs)
        self.log_panel.import_requested.connect(self._import_logs)
        self.log_panel.clear_requested.connect(self._clear_logs)
        self.log_panel.start_live_requested.connect(self._start_live_logs)
        self.log_panel.stop_live_requested.connect(self._stop_live_logs)
        self.log_panel.pause_live_requested.connect(self._pause_live_logs)
        self.log_panel.resume_live_requested.connect(self._resume_live_logs)
        self.log_panel.save_session_toggled.connect(self._set_live_session_save)

        self.add_ku_action.triggered.connect(self._add_ku_step)
        self.add_kt_action.triggered.connect(self._add_kt_step)
        self.add_wait_action.triggered.connect(self._add_wait_step)
        self.add_wait_ts_action.triggered.connect(self._add_wait_ts_step)
        self.add_expected_response_action.triggered.connect(self._insert_expected_response_after_current)

        self.add_ku_button.clicked.connect(self._add_ku_step)
        self.add_kt_button.clicked.connect(self._add_kt_step)
        self.add_wait_button.clicked.connect(self._add_wait_step)
        self.add_wait_ts_button.clicked.connect(self._add_wait_ts_step)
        self.add_expected_response_button.clicked.connect(self._insert_expected_response_after_current)

        self.delete_step_action.triggered.connect(self._delete_selected_step)
        self.move_step_up_action.triggered.connect(self._move_selected_step_up)
        self.move_step_down_action.triggered.connect(self._move_selected_step_down)
        self.duplicate_step_action.triggered.connect(self._duplicate_selected_step)
        self.move_step_to_top_action.triggered.connect(self._move_selected_step_to_top)
        self.move_step_to_bottom_action.triggered.connect(self._move_selected_step_to_bottom)

        self.table_view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.log_panel.table.selectionModel().selectionChanged.connect(self._on_log_selection_changed)
        self.inspector_panel.changed.connect(self._on_step_changed)
        self.timeline_panel.row_clicked.connect(self._on_timeline_row_clicked)

        self.language_ru_action.triggered.connect(lambda: self._set_ui_language("ru"))
        self.language_en_action.triggered.connect(lambda: self._set_ui_language("en"))

    def _new_document(self) -> None:
        self.document = ScenarioDocument(
            schema_version=1,
            metadata=ScenarioMetadata(name="Untitled scenario"),
            validation=ValidationProfile(),
            steps=[],
        )
        self.current_path = None
        self.log_records = []
        self.log_panel.set_records(self.log_records)
        self.table_model.set_document(self.document)
        self.inspector_panel.set_step(None)
        self._refresh_all_views()

    def _open_document(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Open scenario",
            "",
            "JSON files (*.json);;All files (*)",
        )
        if not path_str:
            return

        try:
            loaded = load_scenario(path_str)
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return

        self.document = loaded
        self.current_path = Path(path_str)
        self.log_records = []
        self.log_panel.set_records(self.log_records)
        self.table_model.set_document(self.document)
        self.inspector_panel.set_step(None)
        self._refresh_all_views()

    def _save_document(self) -> None:
        if self.current_path is None:
            self._save_document_as()
            return

        try:
            save_scenario(self.document, self.current_path)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def _save_document_as(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Save scenario",
            "",
            "JSON files (*.json);;All files (*)",
        )
        if not path_str:
            return

        self.current_path = Path(path_str)
        self._save_document()

    def _export_packed_json(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Export packed scenario",
            "",
            "JSON files (*.json);;All files (*)",
        )
        if not path_str:
            return

        try:
            save_packed_scenario_export(self.document, path_str)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _export_generated_c(self) -> None:
        output_dir = QFileDialog.getExistingDirectory(
            self,
            tr("dialog.export_generated_c"),
            "",
        )
        if not output_dir:
            return

        try:
            save_generated_scenario_files(self.document, output_dir)
        except Exception as exc:
            QMessageBox.critical(self, tr("dialog.export_failed_title"), str(exc))

    def _set_ui_language(self, language: str) -> None:
        set_language(language)
        self.retranslate_ui()

        self.table_model.layoutChanged.emit()
        self.warnings_model.layoutChanged.emit()
        self.log_panel.model.layoutChanged.emit()

        self.table_model.headerDataChanged.emit(
            Qt.Orientation.Horizontal,
            0,
            self.table_model.columnCount() - 1,
        )
        self.warnings_model.headerDataChanged.emit(
            Qt.Orientation.Horizontal,
            0,
            self.warnings_model.columnCount() - 1,
        )
        self.log_panel.model.headerDataChanged.emit(
            Qt.Orientation.Horizontal,
            0,
            self.log_panel.model.columnCount() - 1,
        )

        self.timeline_panel.update()

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("app.title"))

        self.new_action.setText(tr("action.new"))
        self.open_action.setText(tr("action.open"))
        self.save_action.setText(tr("action.save"))
        self.save_as_action.setText(tr("action.save_as"))
        self.export_packed_json_action.setText(tr("action.export_packed_json"))
        self.export_generated_c_action.setText(tr("action.export_generated_c"))
        self.import_logs_action.setText(tr("action.import_logs"))

        self.add_ku_action.setText(tr("action.add_ku"))
        self.add_kt_action.setText(tr("action.add_kt"))
        self.add_wait_action.setText(tr("action.add_wait"))
        self.add_wait_ts_action.setText(tr("action.add_wait_ts"))
        self.add_expected_response_action.setText(tr("action.add_expected_response"))

        self.delete_step_action.setText(tr("action.delete_step"))
        self.move_step_up_action.setText(tr("action.move_step_up"))
        self.move_step_down_action.setText(tr("action.move_step_down"))
        self.duplicate_step_action.setText(tr("action.duplicate_step"))
        self.move_step_to_top_action.setText(tr("action.move_step_to_top"))
        self.move_step_to_bottom_action.setText(tr("action.move_step_to_bottom"))

        self.language_ru_action.setText(tr("language.ru"))
        self.language_en_action.setText(tr("language.en"))

        self.file_menu.setTitle(tr("menu.file"))
        self.edit_menu.setTitle(tr("menu.edit"))
        self.language_menu.setTitle(tr("menu.language"))

        self.language_ru_action.setChecked(get_language() == "ru")
        self.language_en_action.setChecked(get_language() == "en")

        self.add_ku_button.setText(tr("button.add_ku"))
        self.add_kt_button.setText(tr("button.add_kt"))
        self.add_wait_button.setText(tr("button.add_wait"))
        self.add_wait_ts_button.setText(tr("button.add_wait_ts"))
        self.add_expected_response_button.setText(tr("button.add_expected_response"))

        self.bottom_tabs.setTabText(self.bottom_tabs.indexOf(self.log_panel), tr("tab.logs"))
        self.bottom_tabs.setTabText(self.bottom_tabs.indexOf(self.warnings_view), tr("tab.warnings"))

        self.log_panel.retranslate_ui()
        self.timeline_panel.retranslate_ui()
        self.inspector_panel.retranslate_ui()

        self.table_model.layoutChanged.emit()
        self.warnings_model.layoutChanged.emit()
        self.log_panel.model.layoutChanged.emit()

        self.table_view.horizontalHeader().viewport().update()
        self.warnings_view.horizontalHeader().viewport().update()
        self.log_panel.table.horizontalHeader().viewport().update()

    def _selected_row(self) -> int | None:
        indexes = self.table_view.selectionModel().selectedRows()
        if not indexes:
            return None
        return indexes[0].row()

    def _insert_expected_response_after_current(self) -> None:
        row = self._selected_row()
        if row is None or not (0 <= row < len(self.document.steps)):
            QMessageBox.information(
                self,
                tr("dialog.expected_response_invalid_title"),
                tr("dialog.expected_response_invalid_text"),
            )
            return

        step = self.document.steps[row]
        if not isinstance(step, SendMessageStep) or step.message is None or step.message.msg_id is None:
            QMessageBox.information(
                self,
                tr("dialog.expected_response_invalid_title"),
                tr("dialog.expected_response_invalid_text"),
            )
            return

        specs = get_expected_responses(step.message.category, step.message.msg_id)
        if not specs:
            QMessageBox.information(
                self,
                tr("dialog.no_expected_response_title"),
                tr("dialog.no_expected_response_text"),
            )
            return

        next_row = row + 1

        # Если вся ожидаемая цепочка уже стоит сразу после send-step, второй раз не вставляем.
        already_exists = True
        for offset, spec in enumerate(specs):
            check_row = next_row + offset
            if check_row >= len(self.document.steps):
                already_exists = False
                break

            existing_step = self.document.steps[check_row]
            if not isinstance(existing_step, WaitForTsStep):
                already_exists = False
                break

            if existing_step.expected is None:
                already_exists = False
                break

            if existing_step.expected.category != spec.category or existing_step.expected.msg_id != spec.msg_id:
                already_exists = False
                break

        if already_exists:
            QMessageBox.information(
                self,
                tr("dialog.expected_response_exists_title"),
                tr("dialog.expected_response_exists_text"),
            )
            return

        new_steps: list[WaitForTsStep] = []
        ts_messages = self.catalog.get_ts_messages()

        for spec in specs:
            ts_name = ""
            for msg in ts_messages:
                if msg.category == spec.category and msg.msg_id == spec.msg_id:
                    ts_name = msg.name
                    break

            new_steps.append(
                WaitForTsStep(
                    id=self._new_step_id(),
                    kind=StepKind.WAIT_FOR_TS,
                    title="",
                    comment="",
                    enabled=True,
                    expected=MessageRef(category=spec.category, msg_id=spec.msg_id, name=ts_name),
                    timeout_ms=spec.timeout_ms,
                    bind_to_previous_ku=spec.bind_to_previous_ku,
                    ack_for_msg_id=step.message.msg_id if spec.is_ack else None,
                    require_ack_ok=spec.require_ack_ok,
                )
            )

        for offset, new_step in enumerate(new_steps):
            self.document.steps.insert(next_row + offset, new_step)

        self.table_model.refresh()
        self._refresh_all_views()
        self._select_row(next_row)

    def _import_logs(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Import logs",
            "",
            "JSON files (*.json);;All files (*)",
        )
        if not path_str:
            return

        try:
            self.log_records = load_log_records(path_str)
        except Exception as exc:
            QMessageBox.critical(self, "Import logs failed", str(exc))
            return

        self._refresh_all_views()

    def _clear_logs(self) -> None:
        self.log_records = []
        self._refresh_all_views()

    def _start_live_logs(self, port1: str, port2: str, baud: int) -> None:
        self._stop_live_logs()

        ports = []
        if port1:
            ports.append(port1)
        if port2 and port2 != port1:
            ports.append(port2)

        if not ports:
            self.log_panel.set_live_status_text(
                tr("status.live_prefix", text=tr("live.status.no_ports"))
            )
            return

        self.log_panel.set_live_status_text(
            tr("status.live_prefix", text=tr("live.status.starting"))
        )

        for port in ports:
            controller = SerialLogController(port=port, baudrate=baud)
            controller.record_received.connect(self._append_live_log_record)
            controller.status_changed.connect(self._on_live_status_message)
            controller.error_occurred.connect(self._on_live_error_message)
            self._serial_controllers.append(controller)
            controller.start()

    def _stop_live_logs(self) -> None:
        for controller in self._serial_controllers:
            controller.stop()
            controller.deleteLater()
        self._serial_controllers.clear()

        self._close_live_session_file()
        self.log_panel.set_live_status_text(
            tr("status.live_prefix", text=tr("live.status.stopped"))
        )

    def _pause_live_logs(self) -> None:
        if not self._serial_controllers:
            self.log_panel.set_live_status_text(
                tr("status.live_prefix", text=tr("live.status.nothing_to_pause"))
            )
            return

        for controller in self._serial_controllers:
            controller.pause()

        self.log_panel.set_live_status_text(
            tr("status.live_prefix", text=tr("live.status.paused"))
        )

    def _resume_live_logs(self) -> None:
        if not self._serial_controllers:
            self.log_panel.set_live_status_text(
                tr("status.live_prefix", text=tr("live.status.nothing_to_resume"))
            )
            return

        for controller in self._serial_controllers:
            controller.resume()

        self.log_panel.set_live_status_text(
            tr("status.live_prefix", text=tr("live.status.resumed"))
        )

    def _set_live_session_save(self, enabled: bool, path: str) -> None:
        self._live_session_save_enabled = enabled
        self._live_session_save_path = path

        if not enabled:
            self._close_live_session_file()
            return

        if not path:
            self.log_panel.set_live_status_text(
                tr(
                    "status.live_prefix",
                    text=tr("live.status.session_save_enabled_no_path"),
                )
            )
            return

        self._open_live_session_file()

    def _open_live_session_file(self) -> None:
        if not self._live_session_save_enabled or not self._live_session_save_path:
            return

        self._close_live_session_file()

        try:
            self._live_session_file = open(self._live_session_save_path, "a", encoding="utf-8")
            self.log_panel.set_live_status_text(
                tr(
                    "status.live_prefix",
                    text=tr("live.status.saving_session", path=self._live_session_save_path),
                )
            )
        except Exception as exc:
            self._live_session_file = None
            self.log_panel.set_live_status_text(
                tr(
                    "status.live_prefix",
                    text=tr("live.status.save_error", error=str(exc)),
                )
            )

    def _close_live_session_file(self) -> None:
        if self._live_session_file is not None:
            try:
                self._live_session_file.close()
            except Exception:
                pass
            self._live_session_file = None

    def _append_live_log_record(self, record: LogRecord) -> None:
        self.log_records.append(record)

        if self._live_session_save_enabled and self._live_session_save_path:
            if self._live_session_file is None:
                self._open_live_session_file()

            if self._live_session_file is not None:
                try:
                    self._live_session_file.write(format_log_record_line(record) + "\n")
                    self._live_session_file.flush()
                except Exception as exc:
                    self.log_panel.set_live_status_text(
                        tr(
                            "status.live_prefix",
                            text=tr("live.status.save_error", error=str(exc)),
                        )
                    )
                    self._close_live_session_file()

        self._schedule_live_refresh()

    def _schedule_live_refresh(self) -> None:
        if self._live_refresh_pending:
            return

        self._live_refresh_pending = True
        QTimer.singleShot(50, self._apply_live_refresh)

    def _apply_live_refresh(self) -> None:
        self._live_refresh_pending = False
        self._refresh_all_views()

        if self.log_panel.is_auto_scroll_enabled() and self.log_records:
            last_row = len(self.log_records) - 1
            self.log_panel.select_original_row(last_row)

    def _on_live_status_message(self, text: str) -> None:
        self.log_panel.set_live_status_text(tr("status.live_prefix", text=text))

    def _on_live_error_message(self, text: str) -> None:
        self.log_panel.set_live_status_text(tr("status.live_error_prefix", text=text))

    def _new_step_id(self) -> str:
        return str(uuid.uuid4())

    def _add_ku_step(self) -> None:
        messages = self.catalog.get_ku_messages()
        first = messages[0] if messages else None

        step = SendMessageStep(
            id=self._new_step_id(),
            kind=StepKind.SEND_KU,
            title="Send KU",
            message=MessageRef(category="KU", msg_id=first.msg_id, name=first.name) if first else None,
            ack_policy=AckPolicy.EXPECT_ACK,
            ack_timeout_ms=1000,
            retry=RetryPolicy(
                attempts=3,
                retry_delay_ms=0,
                retry_on_timeout=True,
                retry_on_reject=False,
            ),
        )
        self.document.steps.append(step)
        self._refresh_all_views()
        self._select_last_row()

    def _add_kt_step(self) -> None:
        messages = self.catalog.get_kt_messages()
        first = messages[0] if messages else None

        step = SendMessageStep(
            id=self._new_step_id(),
            kind=StepKind.SEND_KT,
            title="Send KT",
            message=MessageRef(category="KT", msg_id=first.msg_id, name=first.name) if first else None,
            ack_policy=AckPolicy.NONE,
            ack_timeout_ms=None,
            retry=RetryPolicy(
                attempts=1,
                retry_delay_ms=0,
                retry_on_timeout=False,
                retry_on_reject=False,
            ),
        )
        self.document.steps.append(step)
        self._refresh_all_views()
        self._select_last_row()

    def _add_wait_step(self) -> None:
        step = WaitTimeStep(
            id=self._new_step_id(),
            kind=StepKind.WAIT_TIME,
            title="Wait",
            delay_ms=1000,
        )
        self.document.steps.append(step)
        self._refresh_all_views()
        self._select_last_row()

    def _add_wait_ts_step(self) -> None:
        messages = self.catalog.get_ts_messages()
        first = messages[0] if messages else None

        step = WaitForTsStep(
            id=self._new_step_id(),
            kind=StepKind.WAIT_FOR_TS,
            title="Wait for TS",
            expected=MessageRef(category="TS", msg_id=first.msg_id, name=first.name) if first else None,
            timeout_ms=1000,
        )
        self.document.steps.append(step)
        self._refresh_all_views()
        self._select_last_row()

    def _selected_row_index(self) -> int | None:
        indexes = self.table_view.selectionModel().selectedRows()
        if not indexes:
            return None
        return indexes[0].row()

    def _select_last_row(self) -> None:
        if not self.document.steps:
            return

        row = len(self.document.steps) - 1
        self._select_row(row)

    def _select_row(self, row: int | None) -> None:
        if self._selection_sync_in_progress:
            return

        self._selection_sync_in_progress = True
        try:
            if row is None or not (0 <= row < len(self.document.steps)):
                self.table_view.clearSelection()
                self.inspector_panel.set_step(None)
                self.timeline_panel.set_selected_row(None)
                self.log_panel.table.clearSelection()
                return

            self.table_view.selectRow(row)
            self.inspector_panel.set_step(self.document.steps[row])
            self.timeline_panel.set_selected_row(row)
            self.table_view.scrollTo(self.table_model.index(row, 0))

            matched_log_row = self._step_to_log_row.get(row)
            if matched_log_row is not None:
                self.log_panel.select_original_row(matched_log_row)
            else:
                self.log_panel.table.clearSelection()
        finally:
            self._selection_sync_in_progress = False

    def _select_log_row(self, row: int | None) -> None:
        if self._selection_sync_in_progress:
            return

        self._selection_sync_in_progress = True
        try:
            if row is None or not (0 <= row < len(self.log_records)):
                self.log_panel.table.clearSelection()
                return

            self.log_panel.select_original_row(row)
        finally:
            self._selection_sync_in_progress = False

    def _delete_selected_step(self) -> None:
        row = self._selected_row_index()
        if row is None:
            return

        del self.document.steps[row]
        self._refresh_all_views()

        if not self.document.steps:
            self._select_row(None)
        else:
            self._select_row(min(row, len(self.document.steps) - 1))

    def _move_selected_step_up(self) -> None:
        row = self._selected_row_index()
        if row is None or row <= 0:
            return

        self.document.steps[row - 1], self.document.steps[row] = (
            self.document.steps[row],
            self.document.steps[row - 1],
        )
        self._refresh_all_views()
        self._select_row(row - 1)

    def _move_selected_step_down(self) -> None:
        row = self._selected_row_index()
        if row is None or row >= len(self.document.steps) - 1:
            return

        self.document.steps[row + 1], self.document.steps[row] = (
            self.document.steps[row],
            self.document.steps[row + 1],
        )
        self._refresh_all_views()
        self._select_row(row + 1)

    def _move_selected_step_to_top(self) -> None:
        row = self._selected_row_index()
        if row is None or row <= 0:
            return

        step = self.document.steps.pop(row)
        self.document.steps.insert(0, step)

        self._refresh_all_views()
        self._select_row(0)

    def _move_selected_step_to_bottom(self) -> None:
        row = self._selected_row_index()
        if row is None or row >= len(self.document.steps) - 1:
            return

        step = self.document.steps.pop(row)
        self.document.steps.append(step)

        self._refresh_all_views()
        self._select_row(len(self.document.steps) - 1)

    def _duplicate_selected_step(self) -> None:
        row = self._selected_row_index()
        if row is None:
            return

        source_step = self.document.steps[row]
        new_step = deepcopy(source_step)
        new_step.id = self._new_step_id()

        self.document.steps.insert(row + 1, new_step)
        self._refresh_all_views()
        self._select_row(row + 1)

    def _on_selection_changed(self) -> None:
        indexes = self.table_view.selectionModel().selectedRows()
        if not indexes:
            self.inspector_panel.set_step(None)
            self.timeline_panel.set_selected_row(None)
            return

        row = indexes[0].row()
        step = self.document.steps[row]
        self.inspector_panel.set_step(step)
        self.timeline_panel.set_selected_row(row)

    def _on_log_selection_changed(self) -> None:
        if self._selection_sync_in_progress:
            return

        log_row = self.log_panel.original_selected_row()
        if log_row is None:
            return

        step_row = self._log_to_step_row.get(log_row)
        if step_row is None:
            return

        self._select_row(step_row)

    def _on_timeline_row_clicked(self, row: int) -> None:
        self._select_row(row)

    def _on_step_changed(self) -> None:
        self.table_model.refresh()
        self._refresh_all_views()

    def _build_row_statuses(self, diagnostics) -> dict[int, str]:
        priority = {
            "neutral": 0,
            "pending": 1,
            "warning": 2,
            "error": 3,
            "ok": 4,
        }

        result: dict[int, str] = {}

        for diagnostic in diagnostics:
            if diagnostic.severity.value == "error":
                status = "error"
            elif diagnostic.severity.value == "warning":
                status = "warning"
            else:
                continue

            current = result.get(diagnostic.step_index, "neutral")
            if priority[status] > priority[current]:
                result[diagnostic.step_index] = status

        return result

    def _is_live_running(self) -> bool:
        return bool(self._serial_controllers)

    def _is_actionable_step(self, step) -> bool:
        return isinstance(step, (SendMessageStep, WaitForTsStep))

    def _find_first_actionable_step_row(self) -> int | None:
        for row_index, step in enumerate(self.document.steps):
            if self._is_actionable_step(step):
                return row_index
        return None

    def _mark_pending_after(
            self,
            row_statuses: dict[int, str],
            step_details: dict[int, str],
            start_row: int,
    ) -> None:
        for row_index in range(start_row, len(self.document.steps)):
            step = self.document.steps[row_index]
            if not self._is_actionable_step(step):
                if isinstance(step, WaitTimeStep) and row_index not in step_details:
                    step_details[row_index] = tr(
                        "execution.wait_not_matched",
                        step=row_index + 1,
                    )
                continue

            if row_index not in row_statuses:
                row_statuses[row_index] = "pending"
                step_details[row_index] = tr(
                    "execution.pending_not_reached",
                    step=row_index + 1,
                )

    def _collect_log_problem_rows(
            self,
            log_records: list[LogRecord],
            step_to_log: dict[int, int],
            log_to_step: dict[int, int],
            step_details: dict[int, str],
    ) -> set[int]:
        result: set[int] = set()

        for log_row in range(len(log_records)):
            if log_row not in log_to_step:
                result.add(log_row)

        for step_row, detail in step_details.items():
            if "source looks unusual" in detail:
                matched_log_row = step_to_log.get(step_row)
                if matched_log_row is not None:
                    result.add(matched_log_row)

        return result

    def _build_log_match_info(
            self,
            log_records: list[LogRecord],
    ) -> tuple[
        dict[int, str],
        dict[int, int],
        dict[int, int],
        dict[int, str],
        dict[int, str],
        int | None,
        int | None,
    ]:
        row_statuses: dict[int, str] = {}
        step_to_log: dict[int, int] = {}
        log_to_step: dict[int, int] = {}
        step_details: dict[int, str] = {}
        log_details: dict[int, str] = {}

        used_indices: set[int] = set()
        search_start = 0
        current_step_row: int | None = None
        first_mismatch_row: int | None = None
        execution_blocked = False

        if not log_records:
            first_actionable = self._find_first_actionable_step_row()
            if first_actionable is not None and self._is_live_running():
                row_statuses[first_actionable] = "current"
                step_details[first_actionable] = tr(
                    "execution.current_first_live",
                    step=first_actionable + 1,
                )
                self._mark_pending_after(row_statuses, step_details, first_actionable + 1)
                return (
                    row_statuses,
                    step_to_log,
                    log_to_step,
                    step_details,
                    log_details,
                    first_actionable,
                    None,
                )

            return (
                row_statuses,
                step_to_log,
                log_to_step,
                step_details,
                log_details,
                current_step_row,
                first_mismatch_row,
            )

        for row_index, step in enumerate(self.document.steps):
            if not self._is_actionable_step(step):
                if isinstance(step, WaitTimeStep):
                    step_details[row_index] = tr(
                        "execution.wait_not_matched",
                        step=row_index + 1,
                    )
                continue

            if execution_blocked:
                if current_step_row is None:
                    current_step_row = row_index
                    row_statuses[row_index] = "current"
                    step_details[row_index] = tr(
                        "execution.current_blocked_here",
                        step=row_index + 1,
                    )
                else:
                    row_statuses[row_index] = "pending"
                    step_details[row_index] = tr(
                        "execution.pending_blocked",
                        step=row_index + 1,
                    )
                continue

            if isinstance(step, SendMessageStep):
                if step.message is None or step.message.msg_id is None:
                    step_details[row_index] = tr("execution.no_message_selected")
                    continue

                expected_direction = "tx"
                expected_category = step.message.category
                expected_msg_id = step.message.msg_id
                expected_sources = {"board", ""}

            else:
                if step.expected is None or step.expected.msg_id is None:
                    step_details[row_index] = tr("execution.no_expected_ts")
                    continue

                expected_direction = "rx"
                expected_category = step.expected.category
                expected_msg_id = step.expected.msg_id
                expected_sources = {"detector", ""}

            match_index = self._find_matching_log_record(
                log_records=log_records,
                used_indices=used_indices,
                start_index=search_start,
                direction=expected_direction,
                category=expected_category,
                msg_id=expected_msg_id,
            )

            if match_index is None:
                next_log = None
                for i in range(search_start, len(log_records)):
                    if i not in used_indices:
                        next_log = (i, log_records[i])
                        break

                if next_log is None:
                    row_statuses[row_index] = "current"
                    if isinstance(step, SendMessageStep):
                        step_details[row_index] = tr(
                            "execution.current_waiting_send",
                            step=row_index + 1,
                            direction=tr(f"log.direction.{expected_direction}"),
                            category=expected_category,
                            msg_id=expected_msg_id,
                        )
                    else:
                        step_details[row_index] = tr(
                            "execution.current_waiting_ts",
                            step=row_index + 1,
                            direction=tr(f"log.direction.{expected_direction}"),
                            category=expected_category,
                            msg_id=expected_msg_id,
                        )
                    current_step_row = row_index
                    execution_blocked = True
                    continue

                next_log_index, next_record = next_log
                row_statuses[row_index] = "error"
                step_details[row_index] = tr(
                    "execution.first_mismatch",
                    step=row_index + 1,
                    direction=tr(f"log.direction.{expected_direction}"),
                    category=expected_category,
                    msg_id=expected_msg_id,
                    log_row=next_log_index + 1,
                    got_direction=tr(f"log.direction.{next_record.direction}"),
                    got_category=next_record.category,
                    got_msg_id=next_record.msg_id,
                    source=normalize_log_source(next_record.source) or tr("log.source.empty"),
                    time=next_record.timestamp_ms,
                )
                current_step_row = row_index
                first_mismatch_row = row_index
                execution_blocked = True
                continue

            for i in range(search_start, match_index):
                if i not in used_indices:
                    extra = log_records[i]
                    log_details[i] = tr(
                        "execution.extra_before_step",
                        step=row_index + 1,
                        log_row=i + 1,
                        direction=tr(f"log.direction.{extra.direction}"),
                        category=extra.category,
                        msg_id=extra.msg_id,
                        source=normalize_log_source(extra.source) or tr("log.source.empty"),
                        time=extra.timestamp_ms,
                    )

            used_indices.add(match_index)
            search_start = match_index + 1

            step_to_log[row_index] = match_index
            log_to_step[match_index] = row_index

            record = log_records[match_index]
            record_source = normalize_log_source(record.source)

            if record_source in expected_sources:
                row_statuses[row_index] = "ok"
                if isinstance(step, SendMessageStep):
                    step_details[row_index] = tr(
                        "execution.matched_send",
                        step=row_index + 1,
                        log_row=match_index + 1,
                        direction=tr(f"log.direction.{record.direction}"),
                        category=record.category,
                        msg_id=record.msg_id,
                        source=record_source or tr("log.source.empty"),
                        time=record.timestamp_ms,
                    )
                    log_details[match_index] = tr(
                        "execution.matched_to_step",
                        step=row_index + 1,
                        category=expected_category,
                        msg_id=expected_msg_id,
                    )
                else:
                    step_details[row_index] = tr(
                        "execution.matched_wait_ts",
                        step=row_index + 1,
                        log_row=match_index + 1,
                        direction=tr(f"log.direction.{record.direction}"),
                        category=record.category,
                        msg_id=record.msg_id,
                        source=record_source or tr("log.source.empty"),
                        time=record.timestamp_ms,
                    )
                    log_details[match_index] = tr(
                        "execution.matched_to_wait_ts",
                        step=row_index + 1,
                        category=expected_category,
                        msg_id=expected_msg_id,
                    )
            else:
                row_statuses[row_index] = "warning"
                step_details[row_index] = tr(
                    "execution.source_unusual_step",
                    step=row_index + 1,
                    log_row=match_index + 1,
                    source=record_source or tr("log.source.empty"),
                    expected=sorted(expected_sources),
                )
                log_details[match_index] = tr(
                    "execution.source_unusual_log",
                    step=row_index + 1,
                )

        if current_step_row is not None:
            self._mark_pending_after(row_statuses, step_details, current_step_row + 1)

        for i, rec in enumerate(log_records):
            rec_source = normalize_log_source(rec.source)
            if i not in log_details:
                log_details[i] = tr(
                    "execution.unmatched_log",
                    log_row=i + 1,
                    direction=tr(f"log.direction.{rec.direction}"),
                    category=rec.category,
                    msg_id=rec.msg_id,
                    source=rec_source or tr("log.source.empty"),
                    time=rec.timestamp_ms,
                )

        return (
            row_statuses,
            step_to_log,
            log_to_step,
            step_details,
            log_details,
            current_step_row,
            first_mismatch_row,
        )

    def _find_matching_log_record(
            self,
            log_records: list[LogRecord],
            used_indices: set[int],
            start_index: int,
            direction: str,
            category: str,
            msg_id: int,
    ) -> int | None:
        for i in range(start_index, len(log_records)):
            if i in used_indices:
                continue

            rec = log_records[i]
            if rec.direction != direction:
                continue
            if rec.category != category:
                continue
            if rec.msg_id != msg_id:
                continue

            return i

        return None

    def _merge_row_statuses(
            self,
            analyzer_statuses: dict[int, str],
            log_statuses: dict[int, str],
    ) -> dict[int, str]:
        priority = {
            "neutral": 0,
            "pending": 1,
            "ok": 2,
            "warning": 3,
            "error": 4,
        }

        merged = dict(log_statuses)

        for row_index, status in analyzer_statuses.items():
            current = merged.get(row_index, "neutral")
            if priority[status] >= priority[current]:
                merged[row_index] = status

        return merged

    def _build_execution_summary(
            self,
            step_to_log: dict[int, int],
            log_to_step: dict[int, int],
            current_step_row: int | None,
            first_mismatch_row: int | None,
    ) -> str:
        total_steps = len(self.document.steps)
        matched_steps = len(step_to_log)
        unmatched_steps = total_steps - matched_steps

        total_logs = len(self.log_records)
        matched_logs = len(log_to_step)
        unmatched_logs = total_logs - matched_logs

        if current_step_row is None:
            current_text = tr("summary.current.none")
        else:
            current_text = tr("summary.current.step", step=current_step_row + 1)

        if first_mismatch_row is None:
            mismatch_text = tr("summary.mismatch.none")
        else:
            mismatch_text = tr("summary.mismatch.step", step=first_mismatch_row + 1)

        return tr(
            "summary.execution",
            current=current_text,
            mismatch=mismatch_text,
            matched_steps=matched_steps,
            total_steps=total_steps,
            unmatched_steps=unmatched_steps,
            matched_logs=matched_logs,
            total_logs=total_logs,
            unmatched_logs=unmatched_logs,
        )

    def _refresh_all_views(self) -> None:
        self.table_model.refresh()
        self._refresh_table_row_heights()
        self._fill_table_width()

        self.log_panel.set_records(self.log_records)

        diagnostics = analyze_scenario(self.document)
        self.warnings_model.set_items(diagnostics)
        self.warnings_view.resizeRowsToContents()
        self._fill_warnings_width()

        analyzer_statuses = self._build_row_statuses(diagnostics)
        (
            log_statuses,
            step_to_log,
            log_to_step,
            step_details,
            log_details,
            current_step_row,
            first_mismatch_row,
        ) = self._build_log_match_info(self.log_records)

        self._step_to_log_row = step_to_log
        self._log_to_step_row = log_to_step
        self._step_execution_details = step_details
        self._log_execution_details = log_details

        row_statuses = self._merge_row_statuses(analyzer_statuses, log_statuses)
        self.table_model.set_row_statuses(row_statuses)
        self.timeline_panel.set_document(self.document, row_statuses=row_statuses)

        problem_rows = self._collect_log_problem_rows(
            self.log_records,
            step_to_log,
            log_to_step,
            step_details,
        )

        self.log_panel.set_matched_rows(set(log_to_step.keys()))
        self.log_panel.set_problem_rows(problem_rows)
        self.log_panel.set_summary_text(
            self._build_execution_summary(
                step_to_log,
                log_to_step,
                current_step_row,
                first_mismatch_row,
            )
        )
        self.log_panel.set_row_tooltips(log_details)

        indexes = self.table_view.selectionModel().selectedRows()
        if indexes:
            selected_row = indexes[0].row()
            self.timeline_panel.set_selected_row(selected_row)

            matched_log_row = self._step_to_log_row.get(selected_row)
            if matched_log_row is not None:
                self._select_log_row(matched_log_row)
            else:
                self._select_log_row(None)
        else:
            self.timeline_panel.set_selected_row(None)
            self._select_log_row(None)
