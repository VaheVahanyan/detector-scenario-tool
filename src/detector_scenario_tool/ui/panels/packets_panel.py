"""Monitor for the science-data packets produced in DUMP mode.

Answers the question the mode exists to answer: how much came out, and how much of it is intact.
Storing the packets is off by default — a full bank is hundreds of megabytes.

The stream arrives over USB, not CAN, so this panel reads a serial port (the FTDI bridge on the
control board, `/dev/ttyUSB0` on Linux) or replays a captured file — never the command bus.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from detector_scenario_tool.i18n import tr
from detector_scenario_tool.services.packet_serial_reader import (
    DEFAULT_BAUDRATE,
    DEFAULT_PORT,
    PacketSerialReader,
)
from detector_scenario_tool.logs.packet_stream import PACKET_BYTES, PacketStream
from detector_scenario_tool.protocol import crc16

#: Read a capture file in chunks so a large dump does not block the UI in one go.
READ_CHUNK = 1 << 20


class PacketsPanel(QWidget):
    storage_changed = Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self.stream = PacketStream()
        self._expected_packets: int | None = None

        self.reader = PacketSerialReader()

        self.port_label = QLabel()
        self.port_edit = QLineEdit(DEFAULT_PORT)
        self.baud_label = QLabel()
        self.baud_combo = QComboBox()
        self.baud_combo.setEditable(True)
        self.baud_combo.addItems(
            ["115200", "230400", "460800", "921600", "1000000", "3000000"]
        )
        self.baud_combo.setCurrentText(str(DEFAULT_BAUDRATE))

        self.start_button = QPushButton()
        self.stop_button = QPushButton()
        self.serial_status_label = QLabel()

        self.load_button = QPushButton()
        self.clear_button = QPushButton()

        self.store_checkbox = QCheckBox()
        self.store_path_edit = QLineEdit()
        self.store_browse_button = QPushButton()

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)

        self.counters_group = QGroupBox()
        self.counters_form = QFormLayout(self.counters_group)

        self.received_label = QLabel("0")
        self.valid_label = QLabel("0")
        self.invalid_label = QLabel("0")
        self.sequence_label = QLabel("0")
        self.truncated_label = QLabel("0")
        self.bytes_label = QLabel("0")
        self.session_label = QLabel("-")

        for widget in (
            self.received_label,
            self.valid_label,
            self.invalid_label,
            self.sequence_label,
            self.truncated_label,
            self.bytes_label,
            self.session_label,
        ):
            self.counters_form.addRow(QLabel(), widget)

        self.crc_notice = QLabel()
        self.crc_notice.setWordWrap(True)
        self.crc_notice.setStyleSheet("color: #e8b04b;")

        self.detect_button = QPushButton()
        self.detect_result = QLabel()
        self.detect_result.setWordWrap(True)

        serial_row = QHBoxLayout()
        serial_row.setContentsMargins(8, 8, 8, 4)
        serial_row.setSpacing(8)
        serial_row.addWidget(self.port_label)
        serial_row.addWidget(self.port_edit)
        serial_row.addWidget(self.baud_label)
        serial_row.addWidget(self.baud_combo)
        serial_row.addWidget(self.start_button)
        serial_row.addWidget(self.stop_button)
        serial_row.addWidget(self.serial_status_label, 1)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(8, 0, 8, 4)
        top_row.addWidget(self.load_button)
        top_row.addWidget(self.clear_button)
        top_row.addStretch(1)

        storage_row = QHBoxLayout()
        storage_row.setContentsMargins(8, 0, 8, 4)
        storage_row.addWidget(self.store_checkbox)
        storage_row.addWidget(self.store_path_edit)
        storage_row.addWidget(self.store_browse_button)

        detect_row = QHBoxLayout()
        detect_row.setContentsMargins(8, 0, 8, 4)
        detect_row.addWidget(self.detect_button)
        detect_row.addWidget(self.detect_result, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(serial_row)
        layout.addLayout(top_row)
        layout.addLayout(storage_row)
        layout.addWidget(self.progress)
        layout.addWidget(self.counters_group)
        layout.addWidget(self.crc_notice)
        layout.addLayout(detect_row)
        layout.addStretch(1)

        self.start_button.clicked.connect(self.start_reading)
        self.stop_button.clicked.connect(self.stop_reading)
        self.reader.data_received.connect(self.feed)
        self.reader.status_changed.connect(self.serial_status_label.setText)
        self.reader.error_occurred.connect(self._on_reader_error)

        self.load_button.clicked.connect(self._browse_capture)
        self.clear_button.clicked.connect(self.clear)
        self.store_checkbox.toggled.connect(self._on_store_toggled)
        self.store_browse_button.clicked.connect(self._browse_store_dir)
        self.detect_button.clicked.connect(self._detect_crc_variant)

        self.retranslate_ui()
        self.refresh()

    # -- feeding -----------------------------------------------------------------------

    def feed(self, data: bytes) -> None:
        self.stream.feed(data)
        self.refresh()

    def start_reading(self) -> bool:
        self.reader.port = self.port_edit.text().strip() or DEFAULT_PORT
        try:
            self.reader.baudrate = int(self.baud_combo.currentText())
        except ValueError:
            self.reader.baudrate = DEFAULT_BAUDRATE

        started = self.reader.start()
        self._update_serial_controls()
        return started

    def stop_reading(self) -> None:
        self.reader.stop()
        self._update_serial_controls()

    def _on_reader_error(self, text: str) -> None:
        self.serial_status_label.setText(text)
        self._update_serial_controls()

    def _update_serial_controls(self) -> None:
        running = self.reader.is_running
        self.start_button.setEnabled(not running and PacketSerialReader.is_available())
        self.stop_button.setEnabled(running)
        self.port_edit.setEnabled(not running)
        self.baud_combo.setEnabled(not running)

    def load_capture(self, path: str | Path) -> None:
        path = Path(path)
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(READ_CHUNK)
                if not chunk:
                    break
                self.stream.feed(chunk)
        self.refresh()

    def set_expected_packets(self, count: int | None) -> None:
        """From the CMD_DUMP acknowledgement, which carries the count in bytes 5-7."""
        self._expected_packets = count
        self.refresh()

    def clear(self) -> None:
        self.stream.reset()
        self._expected_packets = None
        self.refresh()

    # -- display -----------------------------------------------------------------------

    def refresh(self) -> None:
        stats = self.stream.stats

        self.received_label.setText(str(stats.received))
        # Showing "0 passed" while the polynomial is unknown would read as "0 are good".
        unknown = tr("packets.value.not_checked")
        self.valid_label.setText(str(stats.crc_ok) if stats.crc_configured else unknown)
        self.invalid_label.setText(str(stats.crc_bad) if stats.crc_configured else unknown)
        self.sequence_label.setText(str(stats.out_of_sequence))
        self.truncated_label.setText(str(stats.truncated))
        self.bytes_label.setText(str(stats.bytes_consumed))
        self.session_label.setText(
            ", ".join(str(s) for s in sorted(stats.sessions)) or "-"
        )

        if self._expected_packets:
            self.progress.setMaximum(self._expected_packets)
            self.progress.setValue(min(stats.received, self._expected_packets))
            self.progress.setFormat(
                tr("packets.progress", done=stats.received, total=self._expected_packets)
            )
        else:
            self.progress.setMaximum(0 if stats.received else 1)
            self.progress.setValue(0)
            self.progress.setFormat(tr("packets.progress_unknown", done=stats.received))

        self.crc_notice.setVisible(not stats.crc_configured)
        self.detect_button.setEnabled(
            not stats.crc_configured and self.stream.store_packets and bool(self.stream.packets)
        )

    def _detect_crc_variant(self) -> None:
        """Work the unknown polynomial out from a captured packet instead of guessing."""
        if not self.stream.packets:
            self.detect_result.setText(tr("packets.detect.no_packets"))
            return

        candidates = None
        for packet in self.stream.packets[:8]:
            matches = set(crc16.detect_variant(packet.core, packet.crc))
            candidates = matches if candidates is None else (candidates & matches)

        if not candidates:
            self.detect_result.setText(tr("packets.detect.none"))
        else:
            self.detect_result.setText(
                tr("packets.detect.found", names=", ".join(sorted(v.name for v in candidates)))
            )

    # -- plumbing ----------------------------------------------------------------------

    def _browse_capture(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("packets.load"),
            "",
            f'{tr("packets.filter")};;{tr("filter.all_files")}',
        )
        if path:
            self.load_capture(path)

    def _browse_store_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, tr("packets.store_dir"), "")
        if directory:
            self.store_path_edit.setText(directory)
            if self.store_checkbox.isChecked():
                self._on_store_toggled(True)

    def _on_store_toggled(self, enabled: bool) -> None:
        self.stream.store_packets = enabled
        if not enabled:
            self.stream.packets.clear()
        self.storage_changed.emit(enabled, self.store_path_edit.text().strip())
        self.refresh()

    def save_stored_packets(self, directory: str | Path) -> int:
        """Write what was kept. Returns how many files were written."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)

        for packet in self.stream.packets:
            name = f"session{packet.session_id:05d}_pkt{packet.number:06d}.bin"
            (directory / name).write_bytes(packet.raw)
        return len(self.stream.packets)

    def retranslate_ui(self) -> None:
        self.load_button.setText(tr("packets.load"))
        self.clear_button.setText(tr("packets.clear"))
        self.store_checkbox.setText(tr("packets.store"))
        self.store_checkbox.setToolTip(tr("packets.store.tooltip"))
        self.store_path_edit.setPlaceholderText(tr("packets.store_dir"))
        self.store_browse_button.setText(tr("logs.browse"))
        self.counters_group.setTitle(tr("packets.counters"))
        self.detect_button.setText(tr("packets.detect"))
        self.crc_notice.setText(tr("packets.crc_not_configured"))
        self.port_label.setText(tr("packets.port"))
        self.baud_label.setText(tr("packets.baud"))
        self.start_button.setText(tr("packets.start"))
        self.stop_button.setText(tr("packets.stop"))
        if not PacketSerialReader.is_available():
            self.serial_status_label.setText(tr("packets.serial.pyserial_missing"))
        self._update_serial_controls()

        labels = [
            tr("packets.received"),
            tr("packets.valid"),
            tr("packets.invalid"),
            tr("packets.out_of_sequence"),
            tr("packets.truncated"),
            tr("packets.bytes"),
            tr("packets.sessions"),
        ]
        for row, text in enumerate(labels):
            item = self.counters_form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            if item is not None and isinstance(item.widget(), QLabel):
                item.widget().setText(text)

        self.refresh()
