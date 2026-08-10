"""A payload editor built from a message definition.

One widget class covers every message: spin boxes for integers, combos for fields with named
choices, check boxes for single bits, a hex field for raw blocks. Adding a message to
`protocol/definitions` therefore costs no UI code at all.

`payload_editor_registry` can still register a hand-written editor for a message that needs a
bespoke layout; this is the fallback for everything else.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QWidget,
)

from detector_scenario_tool.i18n import tr
from detector_scenario_tool.protocol.fields import FieldKind, FieldSpec, MessageDef
from detector_scenario_tool.ui.editors.payload_editor_base import PayloadEditorBase

class GenericPayloadEditor(PayloadEditorBase):
    def __init__(self, spec: MessageDef) -> None:
        super().__init__()
        self.spec = spec
        self._widgets: dict[str, QWidget] = {}
        self._labels: dict[str, QLabel] = {}

        self.form = QFormLayout(self)
        self.form.setContentsMargins(0, 0, 0, 0)

        for field_spec in spec.editable_fields:
            widget = self._build_widget(field_spec)
            if widget is None:
                continue

            label = QLabel()
            self.form.addRow(label, widget)
            self._widgets[field_spec.key] = widget
            self._labels[field_spec.key] = label

        self.retranslate_ui()

    def widget_for(self, key: str) -> QWidget | None:
        """The widget editing `key`, for tests and for focusing a field from a diagnostic."""
        return self._widgets.get(key)

    # -- construction ------------------------------------------------------------------

    def _build_widget(self, field_spec: FieldSpec) -> QWidget | None:
        if field_spec.choices:
            widget = QComboBox()
            for value, label_key in sorted(field_spec.choices.items()):
                widget.addItem(label_key, value)
            widget.currentIndexChanged.connect(self._emit_changed)
            return widget

        if field_spec.is_bitfield and field_spec.bit_length == 1:
            widget = QCheckBox()
            widget.toggled.connect(self._emit_changed)
            return widget

        if field_spec.kind is FieldKind.FLOAT:
            widget = QDoubleSpinBox()
            widget.setDecimals(6)
            widget.setRange(-3.4e38, 3.4e38)
            widget.setKeyboardTracking(False)
            widget.valueChanged.connect(self._emit_changed)
            return widget

        if field_spec.kind is FieldKind.RAW:
            widget = QLineEdit()
            widget.setPlaceholderText(tr("payload.raw_hex_placeholder"))
            widget.editingFinished.connect(self._emit_changed)
            return widget

        widget = QSpinBox()
        low = field_spec.effective_min
        high = field_spec.effective_max
        # QSpinBox is limited to 32-bit; wider fields fall back to that range and rely on the
        # packer's own bounds check.
        widget.setRange(
            max(-2_147_483_648, low if low is not None else 0),
            min(2_147_483_647, high if high is not None else 2_147_483_647),
        )
        widget.setKeyboardTracking(False)
        widget.valueChanged.connect(self._emit_changed)
        return widget

    # -- PayloadEditorBase -------------------------------------------------------------

    def set_payload(self, payload: dict) -> None:
        self._building = True
        try:
            for field_spec in self.spec.editable_fields:
                widget = self._widgets.get(field_spec.key)
                if widget is None:
                    continue

                value = payload.get(field_spec.key, field_spec.default)
                self._set_widget_value(widget, field_spec, value)
        finally:
            self._building = False

    def write_payload(self, payload: dict) -> None:
        for field_spec in self.spec.editable_fields:
            widget = self._widgets.get(field_spec.key)
            if widget is None:
                continue
            payload[field_spec.key] = self._widget_value(widget, field_spec)

    def retranslate_ui(self) -> None:
        for key, label in self._labels.items():
            field_spec = self.spec.field(key)
            text = field_spec.label
            if field_spec.unit:
                text = f"{text}, {field_spec.unit}"
            label.setText(text)
            label.setToolTip(self._tooltip(field_spec))

        for key, widget in self._widgets.items():
            field_spec = self.spec.field(key)
            if isinstance(widget, QComboBox):
                self._relabel_combo(widget, field_spec)
            widget.setToolTip(self._tooltip(field_spec))

    def _relabel_combo(self, widget: QComboBox, field_spec: FieldSpec) -> None:
        widget.blockSignals(True)
        for i in range(widget.count()):
            value = widget.itemData(i)
            label_key = field_spec.choices.get(value, "")
            widget.setItemText(i, tr(label_key) if label_key else str(value))
        widget.blockSignals(False)

    def _tooltip(self, field_spec: FieldSpec) -> str:
        parts = [f"{field_spec.key}"]
        first = field_spec.byte_offset + self.spec.content_origin
        last = first + field_spec.byte_length - 1
        byte_range = f"{first}" if first == last else f"{first}–{last}"
        if field_spec.is_bitfield:
            bit_first = field_spec.bit_offset
            bit_last = bit_first + field_spec.bit_length - 1
            bit_range = f"{bit_first}" if bit_first == bit_last else f"{bit_first}–{bit_last}"
            parts.append(tr("payload.tooltip.byte_bits", bytes=byte_range, bits=bit_range))
        else:
            parts.append(tr("payload.tooltip.bytes", bytes=byte_range))
        if field_spec.doc_ref:
            parts.append(field_spec.doc_ref)
        elif self.spec.doc_ref:
            parts.append(self.spec.doc_ref)
        return "\n".join(parts)

    # -- value plumbing ----------------------------------------------------------------

    @staticmethod
    def _set_widget_value(widget: QWidget, field_spec: FieldSpec, value: Any) -> None:
        if isinstance(widget, QComboBox):
            index = widget.findData(value)
            widget.setCurrentIndex(index if index >= 0 else 0)
        elif isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QDoubleSpinBox):
            widget.setValue(float(value or 0.0))
        elif isinstance(widget, QLineEdit):
            if isinstance(value, (bytes, bytearray)):
                widget.setText(" ".join(f"{b:02X}" for b in value))
            else:
                widget.setText(str(value or ""))
        elif isinstance(widget, QSpinBox):
            try:
                widget.setValue(int(value))
            except (TypeError, ValueError):
                widget.setValue(int(field_spec.default or 0))

    @staticmethod
    def _widget_value(widget: QWidget, field_spec: FieldSpec) -> Any:
        if isinstance(widget, QComboBox):
            data = widget.currentData()
            return data if data is not None else field_spec.default
        if isinstance(widget, QCheckBox):
            return int(widget.isChecked())
        if isinstance(widget, QDoubleSpinBox):
            return widget.value()
        if isinstance(widget, QLineEdit):
            return widget.text().strip()
        if isinstance(widget, QSpinBox):
            return widget.value()
        return field_spec.default

    def _emit_changed(self) -> None:
        if self._building:
            return
        self.changed.emit()
