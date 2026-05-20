from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from detector_scenario_tool.domain.scenario import (
    AckPolicy,
    MessageRef,
    RetryPolicy,
    SendMessageStep,
    StepKind,
    WaitForTsStep,
    WaitTimeStep,
)
from detector_scenario_tool.i18n import tr
from detector_scenario_tool.protocol.catalog import ProtocolCatalog
from detector_scenario_tool.protocol.expected_responses import get_send_defaults
from detector_scenario_tool.protocol.message_lengths import get_expected_message_length
from detector_scenario_tool.protocol.packers import pack_send_message_step, payload_to_hex
from detector_scenario_tool.ui.editors.payload_editor_registry import build_payload_editor_registry


class InspectorPanel(QWidget):
    changed = Signal()

    def __init__(self, catalog: ProtocolCatalog) -> None:
        super().__init__()
        self.catalog = catalog
        self.current_step = None
        self._building = False

        self.payload_editors = build_payload_editor_registry()
        self.current_payload_editor = None

        for editor in self.payload_editors.values():
            editor.changed.connect(self._apply_message_page)

        self.stack = QStackedWidget()

        self.empty_page = QWidget()
        empty_layout = QVBoxLayout(self.empty_page)
        self.empty_label = QLabel()
        empty_layout.addWidget(self.empty_label)

        self.message_page = self._build_message_page()
        self.wait_time_page = self._build_wait_time_page()
        self.wait_ts_page = self._build_wait_ts_page()

        self.stack.addWidget(self.empty_page)
        self.stack.addWidget(self.message_page)
        self.stack.addWidget(self.wait_time_page)
        self.stack.addWidget(self.wait_ts_page)

        layout = QVBoxLayout(self)
        layout.addWidget(self.stack)

        self.retranslate_ui()
        self._set_empty()

    def retranslate_ui(self) -> None:
        self.empty_label.setText(tr("inspector.empty"))

        self.common_group.setTitle(tr("inspector.group.common"))
        self.message_group.setTitle(tr("inspector.group.message"))
        self.retry_group.setTitle(tr("inspector.group.retry"))
        self.payload_group.setTitle(tr("inspector.group.payload"))
        self.pack_group.setTitle(tr("inspector.group.packed_preview"))
        self.wait_time_group.setTitle(tr("inspector.group.wait_time"))
        self.wait_ts_group.setTitle(tr("inspector.group.wait_for_ts"))

        self.payload_info_label.setText(tr("inspector.payload.no_specialized_editor"))

        self.msg_ack_policy.blockSignals(True)
        current_ack = self.msg_ack_policy.currentData()
        self.msg_ack_policy.clear()
        self.msg_ack_policy.addItem(tr("inspector.ack.none"), AckPolicy.NONE.value)
        self.msg_ack_policy.addItem(tr("inspector.ack.expect"), AckPolicy.EXPECT_ACK.value)
        self.msg_ack_policy.addItem(tr("inspector.ack.optional"), AckPolicy.OPTIONAL_ACK.value)
        idx = self.msg_ack_policy.findData(current_ack if current_ack is not None else AckPolicy.NONE.value)
        self.msg_ack_policy.setCurrentIndex(idx if idx >= 0 else 0)
        self.msg_ack_policy.blockSignals(False)

        self._retranslate_message_selector()
        self._retranslate_wait_ts_selector()

        self._retranslate_form(self.common_form, [
            tr("inspector.field.title"),
            tr("inspector.field.enabled"),
            tr("inspector.field.comment"),
        ])
        self._retranslate_form(self.message_form, [
            tr("inspector.field.message"),
            tr("inspector.field.ack_policy"),
            tr("inspector.field.ack_timeout_ms"),
        ])
        self._retranslate_form(self.retry_form, [
            tr("inspector.field.retry_attempts"),
            tr("inspector.field.retry_delay_ms"),
            tr("inspector.field.retry_on_timeout"),
            tr("inspector.field.retry_on_reject"),
        ])
        self._retranslate_form(self.pack_form, [
            tr("inspector.field.pack_status"),
            tr("inspector.field.expected_length"),
            tr("inspector.field.actual_length"),
            tr("inspector.field.hex"),
        ])
        self._retranslate_form(self.wait_time_form, [
            tr("inspector.field.title"),
            tr("inspector.field.enabled"),
            tr("inspector.field.delay_ms"),
            tr("inspector.field.comment"),
        ])
        self._retranslate_form(self.wait_ts_form, [
            tr("inspector.field.title"),
            tr("inspector.field.enabled"),
            tr("inspector.field.expected_ts"),
            tr("inspector.field.timeout_ms"),
            tr("inspector.field.bind_to_previous_ku"),
            tr("inspector.field.ack_for_msg_id"),
            tr("inspector.field.require_ack_accepted"),
            tr("inspector.field.comment"),
        ])

        if hasattr(self.current_payload_editor, "retranslate_ui"):
            self.current_payload_editor.retranslate_ui()

        if isinstance(self.current_step, SendMessageStep):
            self._update_pack_preview(self.current_step)

    def _retranslate_form(self, form: QFormLayout, labels: list[str]) -> None:
        for row, text in enumerate(labels):
            item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            if item is None:
                continue
            widget = item.widget()
            if isinstance(widget, QLabel):
                widget.setText(text)

    def _build_message_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.common_group = QGroupBox()
        self.common_form = QFormLayout(self.common_group)

        self.msg_title_edit = QLineEdit()
        self.msg_comment_edit = QPlainTextEdit()
        self._setup_autogrow_comment_edit(self.msg_comment_edit)
        self.msg_enabled_checkbox = QCheckBox()

        self.common_form.addRow(QLabel(), self.msg_title_edit)
        self.common_form.addRow(QLabel(), self.msg_enabled_checkbox)
        self.common_form.addRow(QLabel(), self.msg_comment_edit)

        self.message_group = QGroupBox()
        self.message_form = QFormLayout(self.message_group)

        self.msg_selector = QComboBox()
        self.msg_ack_policy = QComboBox()

        self.msg_ack_timeout = QSpinBox()
        self.msg_ack_timeout.setRange(0, 60_000)
        self.msg_ack_timeout.setSingleStep(100)

        self.message_form.addRow(QLabel(), self.msg_selector)
        self.message_form.addRow(QLabel(), self.msg_ack_policy)
        self.message_form.addRow(QLabel(), self.msg_ack_timeout)

        self.retry_group = QGroupBox()
        self.retry_form = QFormLayout(self.retry_group)

        self.msg_retry_attempts = QSpinBox()
        self.msg_retry_attempts.setRange(1, 255)

        self.msg_retry_delay_ms = QSpinBox()
        self.msg_retry_delay_ms.setRange(0, 60_000)
        self.msg_retry_delay_ms.setSingleStep(100)

        self.msg_retry_on_timeout = QCheckBox()
        self.msg_retry_on_reject = QCheckBox()

        self.retry_form.addRow(QLabel(), self.msg_retry_attempts)
        self.retry_form.addRow(QLabel(), self.msg_retry_delay_ms)
        self.retry_form.addRow(QLabel(), self.msg_retry_on_timeout)
        self.retry_form.addRow(QLabel(), self.msg_retry_on_reject)

        self.payload_group = QGroupBox()
        payload_layout = QVBoxLayout(self.payload_group)

        self.payload_info_label = QLabel()
        payload_layout.addWidget(self.payload_info_label)

        self.payload_editor_host = QWidget()
        self.payload_editor_host_layout = QVBoxLayout(self.payload_editor_host)
        self.payload_editor_host_layout.setContentsMargins(0, 0, 0, 0)
        payload_layout.addWidget(self.payload_editor_host)

        self.pack_group = QGroupBox()
        self.pack_form = QFormLayout(self.pack_group)

        self.pack_status_label = QLabel("-")
        self.pack_expected_length_label = QLabel("-")
        self.pack_actual_length_label = QLabel("-")
        self.pack_hex_view = QTextEdit()
        self.pack_hex_view.setReadOnly(True)
        self.pack_hex_view.setMinimumHeight(120)

        self.pack_form.addRow(QLabel(), self.pack_status_label)
        self.pack_form.addRow(QLabel(), self.pack_expected_length_label)
        self.pack_form.addRow(QLabel(), self.pack_actual_length_label)
        self.pack_form.addRow(QLabel(), self.pack_hex_view)

        layout.addWidget(self.common_group)
        layout.addWidget(self.message_group)
        layout.addWidget(self.retry_group)
        layout.addWidget(self.payload_group)
        layout.addWidget(self.pack_group)
        layout.addStretch(1)

        self.msg_title_edit.textChanged.connect(self._apply_message_page)
        self.msg_comment_edit.textChanged.connect(self._apply_message_page)
        self.msg_enabled_checkbox.stateChanged.connect(self._apply_message_page)
        self.msg_selector.currentIndexChanged.connect(self._apply_message_page)
        self.msg_ack_policy.currentIndexChanged.connect(self._apply_message_page)
        self.msg_ack_timeout.valueChanged.connect(self._apply_message_page)

        self.msg_retry_attempts.valueChanged.connect(self._apply_message_page)
        self.msg_retry_delay_ms.valueChanged.connect(self._apply_message_page)
        self.msg_retry_on_timeout.stateChanged.connect(self._apply_message_page)
        self.msg_retry_on_reject.stateChanged.connect(self._apply_message_page)

        return page

    def _build_wait_time_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.wait_time_group = QGroupBox()
        self.wait_time_form = QFormLayout(self.wait_time_group)

        self.wait_title_edit = QLineEdit()
        self.wait_comment_edit = QPlainTextEdit()
        self._setup_autogrow_comment_edit(self.wait_comment_edit)
        self.wait_enabled_checkbox = QCheckBox()
        self.wait_delay_spin = QSpinBox()
        self.wait_delay_spin.setRange(0, 10_000_000)
        self.wait_delay_spin.setSingleStep(100)

        self.wait_time_form.addRow(QLabel(), self.wait_title_edit)
        self.wait_time_form.addRow(QLabel(), self.wait_enabled_checkbox)
        self.wait_time_form.addRow(QLabel(), self.wait_delay_spin)
        self.wait_time_form.addRow(QLabel(), self.wait_comment_edit)

        layout.addWidget(self.wait_time_group)
        layout.addStretch(1)

        self.wait_title_edit.textChanged.connect(self._apply_wait_time_page)
        self.wait_comment_edit.textChanged.connect(self._apply_wait_time_page)
        self.wait_enabled_checkbox.stateChanged.connect(self._apply_wait_time_page)
        self.wait_delay_spin.valueChanged.connect(self._apply_wait_time_page)

        return page

    def _build_wait_ts_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.wait_ts_group = QGroupBox()
        self.wait_ts_form = QFormLayout(self.wait_ts_group)

        self.wait_ts_title_edit = QLineEdit()
        self.wait_ts_comment_edit = QPlainTextEdit()
        self._setup_autogrow_comment_edit(self.wait_ts_comment_edit)
        self.wait_ts_enabled_checkbox = QCheckBox()
        self.wait_ts_selector = QComboBox()
        self.wait_ts_timeout_spin = QSpinBox()
        self.wait_ts_timeout_spin.setRange(0, 10_000_000)
        self.wait_ts_timeout_spin.setSingleStep(100)

        self.wait_ts_bind_prev_ku_checkbox = QCheckBox()
        self.wait_ts_ack_for_msg_id_spin = QSpinBox()
        self.wait_ts_ack_for_msg_id_spin.setRange(0, 0xFFFF)

        self.wait_ts_require_ack_ok_checkbox = QCheckBox()

        self.wait_ts_form.addRow(QLabel(), self.wait_ts_title_edit)
        self.wait_ts_form.addRow(QLabel(), self.wait_ts_enabled_checkbox)
        self.wait_ts_form.addRow(QLabel(), self.wait_ts_selector)
        self.wait_ts_form.addRow(QLabel(), self.wait_ts_timeout_spin)
        self.wait_ts_form.addRow(QLabel(), self.wait_ts_bind_prev_ku_checkbox)
        self.wait_ts_form.addRow(QLabel(), self.wait_ts_ack_for_msg_id_spin)
        self.wait_ts_form.addRow(QLabel(), self.wait_ts_require_ack_ok_checkbox)
        self.wait_ts_form.addRow(QLabel(), self.wait_ts_comment_edit)

        layout.addWidget(self.wait_ts_group)
        layout.addStretch(1)

        self.wait_ts_title_edit.textChanged.connect(self._apply_wait_ts_page)
        self.wait_ts_comment_edit.textChanged.connect(self._apply_wait_ts_page)
        self.wait_ts_enabled_checkbox.stateChanged.connect(self._apply_wait_ts_page)
        self.wait_ts_selector.currentIndexChanged.connect(self._apply_wait_ts_page)
        self.wait_ts_timeout_spin.valueChanged.connect(self._apply_wait_ts_page)
        self.wait_ts_bind_prev_ku_checkbox.stateChanged.connect(self._apply_wait_ts_page)
        self.wait_ts_ack_for_msg_id_spin.valueChanged.connect(self._apply_wait_ts_page)
        self.wait_ts_require_ack_ok_checkbox.stateChanged.connect(self._apply_wait_ts_page)

        return page

    def set_step(self, step) -> None:
        self.current_step = step
        self._building = True

        if step is None:
            self._building = False
            self._set_empty()
            return

        if step.kind in (StepKind.SEND_KU, StepKind.SEND_KT):
            self._populate_message_page(step)
            self.stack.setCurrentWidget(self.message_page)
        elif step.kind == StepKind.WAIT_TIME:
            self._populate_wait_time_page(step)
            self.stack.setCurrentWidget(self.wait_time_page)
        elif step.kind == StepKind.WAIT_FOR_TS:
            self._populate_wait_ts_page(step)
            self.stack.setCurrentWidget(self.wait_ts_page)
        else:
            self.stack.setCurrentWidget(self.empty_page)

        self._building = False

    def _set_empty(self) -> None:
        self.stack.setCurrentWidget(self.empty_page)

    def _populate_message_page(self, step: SendMessageStep) -> None:
        self.msg_title_edit.setText(step.title)
        self.msg_comment_edit.setPlainText(step.comment)
        self.msg_enabled_checkbox.setChecked(step.enabled)

        self._retranslate_message_selector(step)

        ack_value = step.ack_policy.value
        idx = self.msg_ack_policy.findData(ack_value)
        self.msg_ack_policy.setCurrentIndex(idx if idx >= 0 else 0)

        self.msg_ack_timeout.setValue(step.ack_timeout_ms or 0)

        self.msg_retry_attempts.setValue(step.retry.attempts)
        self.msg_retry_delay_ms.setValue(step.retry.retry_delay_ms)
        self.msg_retry_on_timeout.setChecked(step.retry.retry_on_timeout)
        self.msg_retry_on_reject.setChecked(step.retry.retry_on_reject)

        self._update_retry_controls_enabled_state(step.ack_policy)
        self._swap_payload_editor(step)
        self._update_pack_preview(step)

    def _update_retry_controls_enabled_state(self, ack_policy: AckPolicy) -> None:
        enable_retry = ack_policy != AckPolicy.NONE
        self.msg_ack_timeout.setEnabled(enable_retry)
        self.msg_retry_attempts.setEnabled(enable_retry)
        self.msg_retry_delay_ms.setEnabled(enable_retry)
        self.msg_retry_on_timeout.setEnabled(enable_retry)
        self.msg_retry_on_reject.setEnabled(enable_retry)

    def _retranslate_message_selector(self, step: SendMessageStep | None = None) -> None:
        current_data = None
        if self.msg_selector.count():
            current_data = self.msg_selector.currentData()

        if step is not None and step.kind in (StepKind.SEND_KU, StepKind.SEND_KT):
            messages = self.catalog.get_ku_messages() if step.kind == StepKind.SEND_KU else self.catalog.get_kt_messages()
            selected_msg_id = step.message.msg_id if step.message is not None else None
        else:
            messages = []
            selected_msg_id = None

        self.msg_selector.blockSignals(True)
        self.msg_selector.clear()

        selected_index = 0
        for i, message in enumerate(messages):
            label = f"0x{message.msg_id:04X} {message.name}"
            data = (message.category, message.msg_id, message.name)
            self.msg_selector.addItem(label, data)

            if selected_msg_id is not None and selected_msg_id == message.msg_id:
                selected_index = i
            elif current_data is not None and current_data[1] == message.msg_id:
                selected_index = i

        if self.msg_selector.count():
            self.msg_selector.setCurrentIndex(selected_index)
        self.msg_selector.blockSignals(False)

    def _swap_payload_editor(self, step: SendMessageStep) -> None:
        while self.payload_editor_host_layout.count():
            item = self.payload_editor_host_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        self.current_payload_editor = None

        if step.message is None or step.message.msg_id is None:
            self.payload_info_label.setVisible(True)
            return

        key = (step.message.category, step.message.msg_id)
        editor = self.payload_editors.get(key)

        if editor is None:
            self.payload_info_label.setVisible(True)
            return

        self.payload_info_label.setVisible(False)
        self.current_payload_editor = editor
        self.payload_editor_host_layout.addWidget(editor)
        editor.set_payload(step.payload)

        if hasattr(editor, "retranslate_ui"):
            editor.retranslate_ui()

    def _update_pack_preview(self, step: SendMessageStep) -> None:
        self.pack_status_label.setText("-")
        self.pack_expected_length_label.setText("-")
        self.pack_actual_length_label.setText("-")
        self.pack_hex_view.setPlainText("")

        if step.message is None or step.message.msg_id is None:
            self.pack_status_label.setText(tr("inspector.pack.no_message_selected"))
            return

        expected_length = get_expected_message_length(
            step.message.category,
            step.message.msg_id,
        )
        if expected_length is not None:
            self.pack_expected_length_label.setText(str(expected_length))

        try:
            packed = pack_send_message_step(step)
            actual_length = len(packed)
            self.pack_actual_length_label.setText(str(actual_length))
            self.pack_hex_view.setPlainText(payload_to_hex(packed))

            if expected_length is None or expected_length == actual_length:
                self.pack_status_label.setText(tr("inspector.pack.ok"))
            else:
                self.pack_status_label.setText(tr("inspector.pack.length_mismatch"))
        except Exception as exc:
            self.pack_status_label.setText(tr("inspector.pack.error", error=str(exc)))
            self.pack_hex_view.setPlainText("")

    def _populate_wait_time_page(self, step: WaitTimeStep) -> None:
        self.wait_title_edit.setText(step.title)
        self.wait_comment_edit.setPlainText(step.comment)
        self.wait_enabled_checkbox.setChecked(step.enabled)
        self.wait_delay_spin.setValue(step.delay_ms)

    def _populate_wait_ts_page(self, step: WaitForTsStep) -> None:
        self.wait_ts_title_edit.setText(step.title)
        self.wait_ts_comment_edit.setPlainText(step.comment)
        self.wait_ts_enabled_checkbox.setChecked(step.enabled)

        self._retranslate_wait_ts_selector(step)

        self.wait_ts_timeout_spin.setValue(step.timeout_ms)
        self.wait_ts_bind_prev_ku_checkbox.setChecked(step.bind_to_previous_ku)
        self.wait_ts_ack_for_msg_id_spin.setValue(step.ack_for_msg_id or 0)
        self.wait_ts_require_ack_ok_checkbox.setChecked(step.require_ack_ok)

        is_ack_wait = (
            step.expected is not None
            and step.expected.category == "TS"
            and step.expected.msg_id == 0x0201
        )
        self.wait_ts_bind_prev_ku_checkbox.setEnabled(is_ack_wait)
        self.wait_ts_ack_for_msg_id_spin.setEnabled(is_ack_wait)
        self.wait_ts_require_ack_ok_checkbox.setEnabled(is_ack_wait)

    def _retranslate_wait_ts_selector(self, step: WaitForTsStep | None = None) -> None:
        current_data = None
        if self.wait_ts_selector.count():
            current_data = self.wait_ts_selector.currentData()

        ts_messages = self.catalog.get_ts_messages()
        selected_msg_id = None
        if step is not None and step.expected is not None:
            selected_msg_id = step.expected.msg_id

        self.wait_ts_selector.blockSignals(True)
        self.wait_ts_selector.clear()

        selected_index = 0
        for i, message in enumerate(ts_messages):
            label = f"0x{message.msg_id:04X} {message.name}"
            data = (message.category, message.msg_id, message.name)
            self.wait_ts_selector.addItem(label, data)

            if selected_msg_id is not None and selected_msg_id == message.msg_id:
                selected_index = i
            elif current_data is not None and current_data[1] == message.msg_id:
                selected_index = i

        if self.wait_ts_selector.count():
            self.wait_ts_selector.setCurrentIndex(selected_index)
        self.wait_ts_selector.blockSignals(False)

    def _apply_message_page(self) -> None:
        if self._building or self.current_step is None:
            return
        if not isinstance(self.current_step, SendMessageStep):
            return

        previous_category = self.current_step.message.category if self.current_step.message is not None else None
        previous_msg_id = self.current_step.message.msg_id if self.current_step.message is not None else None

        self.current_step.title = self.msg_title_edit.text()
        self.current_step.comment = self.msg_comment_edit.toPlainText()
        self.current_step.enabled = self.msg_enabled_checkbox.isChecked()

        data = self.msg_selector.currentData()
        selected_changed = False
        if data is not None:
            category, msg_id, name = data
            self.current_step.message = MessageRef(category=category, msg_id=msg_id, name=name)
            selected_changed = (category != previous_category) or (msg_id != previous_msg_id)

        ack_value = self.msg_ack_policy.currentData()
        if ack_value is not None:
            self.current_step.ack_policy = AckPolicy(ack_value)

        self.current_step.ack_timeout_ms = self.msg_ack_timeout.value()

        self.current_step.retry = RetryPolicy(
            attempts=self.msg_retry_attempts.value(),
            retry_delay_ms=self.msg_retry_delay_ms.value(),
            retry_on_timeout=self.msg_retry_on_timeout.isChecked(),
            retry_on_reject=self.msg_retry_on_reject.isChecked(),
        )

        if selected_changed and self.current_step.message is not None and self.current_step.message.msg_id is not None:
            defaults = get_send_defaults(self.current_step.message.category, self.current_step.message.msg_id)
            if defaults is not None:
                self._building = True
                try:
                    self.current_step.ack_policy = defaults.ack_policy
                    self.current_step.ack_timeout_ms = defaults.ack_timeout_ms
                    self.current_step.retry = RetryPolicy(
                        attempts=defaults.attempts,
                        retry_delay_ms=defaults.retry_delay_ms,
                        retry_on_timeout=defaults.retry_on_timeout,
                        retry_on_reject=defaults.retry_on_reject,
                    )

                    ack_idx = self.msg_ack_policy.findData(defaults.ack_policy.value)
                    self.msg_ack_policy.setCurrentIndex(ack_idx if ack_idx >= 0 else 0)
                    self.msg_ack_timeout.setValue(defaults.ack_timeout_ms or 0)
                    self.msg_retry_attempts.setValue(defaults.attempts)
                    self.msg_retry_delay_ms.setValue(defaults.retry_delay_ms)
                    self.msg_retry_on_timeout.setChecked(defaults.retry_on_timeout)
                    self.msg_retry_on_reject.setChecked(defaults.retry_on_reject)
                finally:
                    self._building = False

        if self.current_step.ack_policy == AckPolicy.NONE:
            self.current_step.ack_timeout_ms = None
            self.current_step.retry.attempts = 1
            self.current_step.retry.retry_delay_ms = 0
            self.current_step.retry.retry_on_timeout = False
            self.current_step.retry.retry_on_reject = False

            self._building = True
            try:
                self.msg_ack_timeout.setValue(0)
                self.msg_retry_attempts.setValue(1)
                self.msg_retry_delay_ms.setValue(0)
                self.msg_retry_on_timeout.setChecked(False)
                self.msg_retry_on_reject.setChecked(False)
            finally:
                self._building = False

        self._update_retry_controls_enabled_state(self.current_step.ack_policy)

        self._apply_payload_to_step(self.current_step)
        self._swap_payload_editor(self.current_step)
        self._update_pack_preview(self.current_step)

        self.changed.emit()

    def _setup_autogrow_comment_edit(self, edit) -> None:
        edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._update_comment_edit_height(edit)
        edit.textChanged.connect(lambda e=edit: self._update_comment_edit_height(e))

    def _update_comment_edit_height(self, edit) -> None:
        document = edit.document()
        line_spacing = edit.fontMetrics().lineSpacing()
        doc_margin = int(document.documentMargin())

        block_count = max(1, document.blockCount())
        visible_blocks = min(block_count, 8)

        height = visible_blocks * line_spacing + doc_margin * 2 + 10
        edit.setFixedHeight(height)

    def _apply_payload_to_step(self, step: SendMessageStep) -> None:
        if self.current_payload_editor is None:
            return

        step.payload.clear()
        self.current_payload_editor.write_payload(step.payload)

    def _apply_wait_time_page(self) -> None:
        if self._building or self.current_step is None:
            return
        if not isinstance(self.current_step, WaitTimeStep):
            return

        self.current_step.title = self.wait_title_edit.text()
        self.current_step.comment = self.wait_comment_edit.toPlainText()
        self.current_step.enabled = self.wait_enabled_checkbox.isChecked()
        self.current_step.delay_ms = self.wait_delay_spin.value()

        self.changed.emit()

    def _apply_wait_ts_page(self) -> None:
        if self._building or self.current_step is None:
            return
        if not isinstance(self.current_step, WaitForTsStep):
            return

        self.current_step.title = self.wait_ts_title_edit.text()
        self.current_step.comment = self.wait_ts_comment_edit.toPlainText()
        self.current_step.enabled = self.wait_ts_enabled_checkbox.isChecked()

        data = self.wait_ts_selector.currentData()
        if data is not None:
            category, msg_id, name = data
            self.current_step.expected = MessageRef(category=category, msg_id=msg_id, name=name)

        self.current_step.timeout_ms = self.wait_ts_timeout_spin.value()

        is_ack_wait = (
            self.current_step.expected is not None
            and self.current_step.expected.category == "TS"
            and self.current_step.expected.msg_id == 0x0201
        )

        self.wait_ts_bind_prev_ku_checkbox.setEnabled(is_ack_wait)
        self.wait_ts_ack_for_msg_id_spin.setEnabled(is_ack_wait)
        self.wait_ts_require_ack_ok_checkbox.setEnabled(is_ack_wait)

        if is_ack_wait:
            self.current_step.bind_to_previous_ku = self.wait_ts_bind_prev_ku_checkbox.isChecked()
            self.current_step.ack_for_msg_id = self.wait_ts_ack_for_msg_id_spin.value() or None
            self.current_step.require_ack_ok = self.wait_ts_require_ack_ok_checkbox.isChecked()
        else:
            self.current_step.bind_to_previous_ku = False
            self.current_step.ack_for_msg_id = None
            self.current_step.require_ack_ok = False

        self.changed.emit()