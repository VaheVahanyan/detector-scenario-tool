"""Connection and run controls.

Dry run is the default and the safe path: it drives the whole runner against a simulated detector,
so a scenario can be exercised end to end before anything reaches hardware. Selecting a real
adapter arms a confirmation before the first transmission and shows a LIVE banner while connected.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from detector_scenario_tool.i18n import tr
from detector_scenario_tool.services import can_interface
from detector_scenario_tool.utils.labels import category_short
from detector_scenario_tool.transport.backend import ConnectionSettings
from detector_scenario_tool.transport.registry import available_backends, get_backend_info
from detector_scenario_tool.transport_defaults import DEFAULT_BITRATE

BITRATES = ("1000000", "500000", "250000", "125000")


class RunPanel(QWidget):
    connect_requested = Signal(object)     # ConnectionSettings
    disconnect_requested = Signal()
    run_requested = Signal()
    pause_requested = Signal()
    resume_requested = Signal()
    stop_requested = Signal()
    step_requested = Signal()

    def __init__(self) -> None:
        super().__init__()

        self.backend_combo = QComboBox()
        for info in available_backends():
            self.backend_combo.addItem(tr(info.label_key), info.name)
            if not info.available:
                index = self.backend_combo.count() - 1
                self.backend_combo.model().item(index).setEnabled(False)

        self.channel_label = QLabel()
        self.channel_edit = QLineEdit()

        self.bitrate_label = QLabel()
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems(BITRATES)
        self.bitrate_combo.setCurrentText(str(DEFAULT_BITRATE))

        # SocketCAN takes its bitrate from the kernel, not from python-can, so the field is only
        # meaningful next to a button that actually applies it.
        self.configure_button = QPushButton()

        self.extended_checkbox = QCheckBox()

        self.connect_button = QPushButton()
        self.disconnect_button = QPushButton()

        self.run_button = QPushButton()
        self.pause_button = QPushButton()
        self.resume_button = QPushButton()
        self.stop_button = QPushButton()
        self.step_button = QPushButton()
        self.continue_on_failure_checkbox = QCheckBox()
        # Master switch for КТ: a bench session often wants the control commands without the
        # data pushes the БВС would normally be making.
        self.send_telemetry_checkbox = QCheckBox()
        self.send_telemetry_checkbox.setChecked(True)

        self.live_banner = QLabel()
        self.live_banner.setVisible(False)
        self.live_banner.setStyleSheet(
            "background-color: #7a1f1f; color: #ffffff; padding: 4px; font-weight: bold;"
        )

        self.status_label = QLabel()

        connection_row = QHBoxLayout()
        connection_row.setContentsMargins(8, 6, 8, 4)
        connection_row.setSpacing(8)
        connection_row.addWidget(self.backend_combo)
        connection_row.addWidget(self.channel_label)
        connection_row.addWidget(self.channel_edit)
        connection_row.addWidget(self.bitrate_label)
        connection_row.addWidget(self.bitrate_combo)
        connection_row.addWidget(self.configure_button)
        connection_row.addWidget(self.extended_checkbox)
        connection_row.addWidget(self.connect_button)
        connection_row.addWidget(self.disconnect_button)
        connection_row.addStretch(1)

        run_row = QHBoxLayout()
        run_row.setContentsMargins(8, 0, 8, 6)
        run_row.setSpacing(8)
        run_row.addWidget(self.run_button)
        run_row.addWidget(self.pause_button)
        run_row.addWidget(self.resume_button)
        run_row.addWidget(self.step_button)
        run_row.addWidget(self.stop_button)
        run_row.addWidget(self.send_telemetry_checkbox)
        run_row.addWidget(self.continue_on_failure_checkbox)
        run_row.addStretch(1)
        run_row.addWidget(self.status_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.live_banner)
        layout.addLayout(connection_row)
        layout.addLayout(run_row)

        self.backend_combo.currentIndexChanged.connect(self._on_backend_changed)
        self.configure_button.clicked.connect(self._configure_interface)
        self.connect_button.clicked.connect(self._emit_connect)
        self.disconnect_button.clicked.connect(self.disconnect_requested.emit)
        self.run_button.clicked.connect(self.run_requested.emit)
        self.pause_button.clicked.connect(self.pause_requested.emit)
        self.resume_button.clicked.connect(self.resume_requested.emit)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.step_button.clicked.connect(self.step_requested.emit)

        self.retranslate_ui()
        self._on_backend_changed()
        self.set_connected(False)
        self.set_run_state("idle")

    # -- state -------------------------------------------------------------------------

    def settings(self) -> ConnectionSettings:
        return ConnectionSettings(
            backend=self.backend_combo.currentData() or "virtual",
            channel=self.channel_edit.text().strip(),
            bitrate=int(self.bitrate_combo.currentText()),
            extended_ids=self.extended_checkbox.isChecked(),
        )

    def apply_settings(self, settings: ConnectionSettings) -> None:
        index = self.backend_combo.findData(settings.backend)
        if index >= 0:
            self.backend_combo.setCurrentIndex(index)
        self.channel_edit.setText(settings.channel)
        self.bitrate_combo.setCurrentText(str(settings.bitrate))
        self.extended_checkbox.setChecked(settings.extended_ids)

    def set_connected(self, connected: bool, simulated: bool = True) -> None:
        self.connect_button.setEnabled(not connected)
        self.disconnect_button.setEnabled(connected)
        self.backend_combo.setEnabled(not connected)
        self.channel_edit.setEnabled(not connected)
        self.bitrate_combo.setEnabled(not connected)
        self.extended_checkbox.setEnabled(not connected)
        self.run_button.setEnabled(connected)
        self.step_button.setEnabled(connected)

        self.live_banner.setVisible(connected and not simulated)
        if connected and not simulated:
            self.live_banner.setText(tr("transport.live_banner"))

    def set_run_state(self, state: str) -> None:
        running = state == "running"
        paused = state == "paused"
        active = running or paused

        self.run_button.setEnabled(not active and self.disconnect_button.isEnabled())
        self.pause_button.setEnabled(running)
        self.resume_button.setEnabled(paused)
        self.stop_button.setEnabled(active)
        self.step_button.setEnabled(not running and self.disconnect_button.isEnabled())

        self.status_label.setText(tr(f"transport.state.{state}"))

    def set_status_text(self, text: str) -> None:
        self.status_label.setText(text)

    def stop_on_failure(self) -> bool:
        return not self.continue_on_failure_checkbox.isChecked()

    def send_telemetry_commands(self) -> bool:
        return self.send_telemetry_checkbox.isChecked()

    # -- plumbing ----------------------------------------------------------------------

    def _configure_interface(self) -> None:
        """Bring the SocketCAN interface up, after saying plainly what will run as root."""
        settings = self.settings()

        problem = can_interface.validate(settings.channel, settings.bitrate)
        if problem is not None:
            QMessageBox.warning(self, tr("transport.configure"), tr(f"diag.{problem}"))
            return

        command = can_interface.describe_command(settings.channel, settings.bitrate)
        answer = QMessageBox.question(
            self,
            tr("transport.configure"),
            tr("transport.configure.confirm", command=command),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Ok,
        )
        if answer != QMessageBox.StandardButton.Ok:
            return

        result = can_interface.configure(settings.channel, settings.bitrate)

        if result.ok:
            self.set_status_text(
                tr("transport.configure.done", channel=settings.channel, bitrate=settings.bitrate)
            )
            return

        if result.cancelled:
            self.set_status_text(tr("transport.configure.cancelled"))
            return

        detail = result.detail
        QMessageBox.critical(
            self,
            tr("transport.configure"),
            tr("transport.configure.failed", detail=tr(f"diag.{detail}") if detail.startswith("caninterface.") else detail),
        )

    def _emit_connect(self) -> None:
        self.connect_requested.emit(self.settings())

    def _on_backend_changed(self) -> None:
        info = get_backend_info(self.backend_combo.currentData() or "virtual")
        needs_channel = bool(info and info.needs_channel)

        self.channel_label.setVisible(needs_channel)
        self.channel_edit.setVisible(needs_channel)
        self.bitrate_label.setVisible(needs_channel)
        self.bitrate_combo.setVisible(needs_channel)

        # slcan sets its own bitrate over the wire; only SocketCAN needs the kernel told.
        needs_root_setup = (self.backend_combo.currentData() or "") == "socketcan"
        self.configure_button.setVisible(needs_root_setup)
        self.configure_button.setEnabled(needs_root_setup and can_interface.is_available())

        if info is not None and info.channel_example and not self.channel_edit.text():
            self.channel_edit.setPlaceholderText(info.channel_example)

    def retranslate_ui(self) -> None:
        current = self.backend_combo.currentData()
        self.backend_combo.blockSignals(True)
        for index in range(self.backend_combo.count()):
            info = get_backend_info(self.backend_combo.itemData(index))
            if info is not None:
                self.backend_combo.setItemText(index, tr(info.label_key))
        restored = self.backend_combo.findData(current)
        if restored >= 0:
            self.backend_combo.setCurrentIndex(restored)
        self.backend_combo.blockSignals(False)

        self.channel_label.setText(tr("transport.channel"))
        self.bitrate_label.setText(tr("transport.bitrate"))
        self.extended_checkbox.setText(tr("transport.extended_ids"))
        self.configure_button.setText(tr("transport.configure"))
        self.configure_button.setToolTip(tr("transport.configure.tooltip"))
        self.connect_button.setText(tr("transport.connect"))
        self.disconnect_button.setText(tr("transport.disconnect"))
        self.run_button.setText(tr("transport.run"))
        self.pause_button.setText(tr("transport.pause"))
        self.resume_button.setText(tr("transport.resume"))
        self.stop_button.setText(tr("transport.stop"))
        self.step_button.setText(tr("transport.step"))
        self.continue_on_failure_checkbox.setText(tr("transport.continue_on_failure"))
        self.send_telemetry_checkbox.setText(
            tr("transport.send_telemetry_commands", category=category_short("KT"))
        )
        self.send_telemetry_checkbox.setToolTip(tr("transport.send_telemetry_commands.tooltip"))
        if self.live_banner.isVisible():
            self.live_banner.setText(tr("transport.live_banner"))
