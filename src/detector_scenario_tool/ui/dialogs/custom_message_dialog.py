"""Authoring one message definition.

The frame format is fixed, so the dialog asks for exactly what varies: identifier, addresses,
length, short or long, content, and whether it repeats. Problems are shown as you type rather than
on OK, because a message with a bad identifier is worth knowing about before it is saved.

`message_catalog_dialog` is what lists them all and drives this one.
"""

from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from detector_scenario_tool.domain.custom_messages import (
    CATEGORIES,
    MAX_CUSTOM_LENGTH,
    CustomBitRange,
    CustomByteLayout,
    CustomMessageSpec,
    validate_spec,
)
from detector_scenario_tool.domain.scenario import CyclicPolicy
from detector_scenario_tool.i18n import tr
from detector_scenario_tool.transport.unican import MAX_SHORT_PAYLOAD
from detector_scenario_tool.ui.widgets.content_editor import ContentEditor
from detector_scenario_tool.utils.labels import category_short

LENGTH_MODE_AUTO = "auto"
LENGTH_MODE_SHORT = "short"
LENGTH_MODE_LONG = "long"


class CustomMessageDialog(QDialog):
    def __init__(
            self,
            spec: CustomMessageSpec | None = None,
            parent: QWidget | None = None,
            siblings: list[CustomMessageSpec] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        self._spec = spec
        #: The other definitions in the same scenario, so a duplicate identifier is caught here
        #: rather than silently later.
        self.siblings = list(siblings or [])
        # The editor works on a copy, so cancelling really cancels.
        self._working = _copy(spec) if spec is not None else CustomMessageSpec()
        self.resize(720, 640)

        self.name_edit = QLineEdit()
        self.category_combo = QComboBox()
        for code in CATEGORIES:
            self.category_combo.addItem(category_short(code), code)

        self.msg_id_edit = QLineEdit()
        self.msg_id_edit.setPlaceholderText("0x0FFF")

        self.length_spin = QSpinBox()
        self.length_spin.setRange(0, MAX_CUSTOM_LENGTH)
        self.length_spin.setKeyboardTracking(False)

        self.framing_combo = QComboBox()
        for mode in (LENGTH_MODE_AUTO, LENGTH_MODE_SHORT, LENGTH_MODE_LONG):
            self.framing_combo.addItem("", mode)

        self.destination_edit = QLineEdit()
        self.source_edit = QLineEdit()

        self.content_editor = ContentEditor()
        self.content_editor.setMinimumHeight(240)

        self.cyclic_checkbox = QCheckBox()
        self.cyclic_period_spin = QSpinBox()
        self.cyclic_period_spin.setRange(1, 3600)
        self.cyclic_period_spin.setSuffix(" s")
        self.cyclic_period_spin.setValue(20)

        self.problems_label = QLabel()
        self.problems_label.setWordWrap(True)
        self.problems_label.setStyleSheet("color: #e8b04b;")

        self.form = QFormLayout()
        self.form.addRow(QLabel(), self.name_edit)
        self.form.addRow(QLabel(), self.category_combo)
        self.form.addRow(QLabel(), self.msg_id_edit)
        self.form.addRow(QLabel(), self.length_spin)
        self.form.addRow(QLabel(), self.framing_combo)
        self.form.addRow(QLabel(), self.destination_edit)
        self.form.addRow(QLabel(), self.source_edit)
        self.form.addRow(QLabel(), self.content_editor)
        self.form.addRow(QLabel(), self.cyclic_checkbox)
        self.form.addRow(QLabel(), self.cyclic_period_spin)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(self.form)
        layout.addWidget(self.problems_label)
        layout.addWidget(self.buttons)

        for widget in (self.name_edit, self.msg_id_edit, self.destination_edit, self.source_edit):
            widget.textEdited.connect(self._revalidate)
        self.content_editor.changed.connect(self._revalidate)
        self.length_spin.valueChanged.connect(self._on_length_changed)
        self.framing_combo.currentIndexChanged.connect(self._revalidate)
        self.category_combo.currentIndexChanged.connect(self._revalidate)
        self.cyclic_checkbox.toggled.connect(self._on_cyclic_toggled)

        self.retranslate_ui()
        self._populate(spec)
        self._revalidate()

    # -- content -----------------------------------------------------------------------

    def _populate(self, spec: CustomMessageSpec | None) -> None:
        if spec is None:
            self.length_spin.setValue(6)
            self._working.length = 6
            self.content_editor.set_spec(self._working)
            self._on_cyclic_toggled(False)
            return

        self.name_edit.setText(spec.name)
        index = self.category_combo.findData(spec.category)
        self.category_combo.setCurrentIndex(max(0, index))
        self.msg_id_edit.setText(f"0x{spec.msg_id:04X}")
        self.length_spin.setValue(spec.length)
        self.framing_combo.setCurrentIndex(
            self.framing_combo.findData(
                LENGTH_MODE_AUTO
                if spec.force_long is None
                else (LENGTH_MODE_LONG if spec.force_long else LENGTH_MODE_SHORT)
            )
        )
        self.destination_edit.setText(
            "" if spec.destination_id is None else f"0x{spec.destination_id:02X}"
        )
        self.source_edit.setText("" if spec.source_id is None else f"0x{spec.source_id:02X}")


        self.content_editor.set_spec(self._working)

        self.cyclic_checkbox.setChecked(bool(spec.cyclic and spec.cyclic.enabled))
        if spec.cyclic is not None:
            self.cyclic_period_spin.setValue(max(1, spec.cyclic.period_ms // 1000))
        self._on_cyclic_toggled(self.cyclic_checkbox.isChecked())

    def result_spec(self) -> CustomMessageSpec:
        framing = self.framing_combo.currentData()
        cyclic = (
            CyclicPolicy(enabled=True, period_ms=self.cyclic_period_spin.value() * 1000)
            if self.cyclic_checkbox.isChecked()
            else None
        )

        spec = CustomMessageSpec(
            layout=[_copy_layout(entry) for entry in self._working.layout],
            name=self.name_edit.text().strip(),
            category=self.category_combo.currentData(),
            msg_id=_parse_int(self.msg_id_edit.text(), 0),
            length=self.length_spin.value(),
            content_hex=self._working.content_hex,
            force_long=None if framing == LENGTH_MODE_AUTO else framing == LENGTH_MODE_LONG,
            destination_id=_parse_optional_int(self.destination_edit.text()),
            source_id=_parse_optional_int(self.source_edit.text()),
            cyclic=cyclic,
        )
        if self._spec is not None:
            spec.id = self._spec.id
        return spec

    # -- feedback ----------------------------------------------------------------------

    def _on_length_changed(self) -> None:
        self._working.length = self.length_spin.value()
        self._working.trim_layout()
        self.content_editor.set_spec(self._working)
        self._revalidate()

    def _revalidate(self) -> None:
        spec = self.result_spec()
        issues = validate_spec(spec, self.siblings)

        blocking = [code for code, _ in issues if code in _BLOCKING]
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not blocking)

        if issues:
            self.problems_label.setText(
                "\n".join(tr(f"diag.{code}", **params) for code, params in issues)
            )
        else:
            self.problems_label.setText(
                tr("custom.summary", framing=tr(f"custom.framing.{'long' if spec.is_long else 'short'}"),
                   length=spec.length)
            )

    def _on_cyclic_toggled(self, enabled: bool) -> None:
        self.cyclic_period_spin.setEnabled(enabled)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("custom.dialog.title"))

        labels = [
            tr("custom.field.name"),
            tr("custom.field.category"),
            tr("custom.field.msg_id"),
            tr("custom.field.length"),
            tr("custom.field.framing"),
            tr("custom.field.destination"),
            tr("custom.field.source"),
            tr("custom.field.content"),
            tr("inspector.field.cyclic_enabled"),
            tr("inspector.field.cyclic_period"),
        ]
        for row, text in enumerate(labels):
            item = self.form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            if item is not None and isinstance(item.widget(), QLabel):
                item.widget().setText(text)

        for index, mode in enumerate((LENGTH_MODE_AUTO, LENGTH_MODE_SHORT, LENGTH_MODE_LONG)):
            self.framing_combo.setItemText(index, tr(f"custom.framing.{mode}"))

        self.destination_edit.setPlaceholderText(tr("custom.address_placeholder"))
        self.source_edit.setPlaceholderText(tr("custom.address_placeholder"))


#: Problems that make the definition unusable rather than merely questionable. Shadowing a
#: catalogue command is here because the registry would refuse it anyway.
_BLOCKING = {
    "custom.unusable_msg_id",
    "custom.content_not_hex",
    "custom.address_out_of_range",
    "custom.shadows_catalogue",
    "custom.duplicate_msg_id",
}


def _copy_layout(entry: CustomByteLayout) -> CustomByteLayout:
    return CustomByteLayout(
        name=entry.name,
        bits=[
            CustomBitRange(name=b.name, offset=b.offset, length=b.length) for b in entry.bits
        ],
    )


def _copy(spec: CustomMessageSpec) -> CustomMessageSpec:
    """A deep copy, so editing a dialog's working copy cannot touch the caller's list.

    Copying field by field is how a newly added field silently goes missing — `overrides_builtin`
    did exactly that once — so this copies everything.
    """
    return copy.deepcopy(spec)


def _parse_int(text: str, default: int) -> int:
    text = text.strip()
    if not text:
        return default
    try:
        return int(text, 16) if text.lower().startswith("0x") else int(text, 0)
    except ValueError:
        try:
            return int(text, 16)
        except ValueError:
            return default


def _parse_optional_int(text: str) -> int | None:
    return None if not text.strip() else _parse_int(text, 0)
