"""Shared input behaviour for editable panels.

Applied centrally rather than widget by widget, so editors added later inherit it without having
to remember anything.
"""

from __future__ import annotations

from PySide6.QtWidgets import QAbstractSpinBox, QWidget


def apply_deferred_commit(root: QWidget) -> None:
    """Stop spin boxes from committing a value on every keystroke.

    With keyboard tracking on, typing "12345" walks the model through 1, 12, 123, 1234, 12345 —
    each an edit that re-runs validation and, worse, gets clamped to the widget's range while
    still half-typed. With it off, the value commits on Enter, on focus loss or on the arrows.
    """
    for spin in root.findChildren(QAbstractSpinBox):
        spin.setKeyboardTracking(False)


def commit_pending_edits(root: QWidget) -> None:
    """Force the spin box currently being typed into to commit its text.

    Needed before saving or exporting: without it, a value typed but not yet confirmed by
    Enter or focus loss would silently not be part of the saved document.
    """
    for spin in root.findChildren(QAbstractSpinBox):
        if spin.hasFocus():
            spin.interpretText()
