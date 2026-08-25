"""No user-visible string may bypass the translation layer.

A literal passed straight to `setText`, a dialog caption or a file filter is invisible until
someone switches the language and finds a stray English word in a Russian UI. This scans the
package's AST instead of relying on anyone noticing.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "detector_scenario_tool"

#: Calls whose text argument is shown to the user, mapped to the positions of those arguments.
#: `addItem(text, userData)` — only the first argument is displayed.
DISPLAY_ARGUMENTS: dict[str, tuple[int, ...]] = {
    "setText": (0,),
    "setWindowTitle": (0,),
    "setPlaceholderText": (0,),
    "setToolTip": (0,),
    "setTitle": (0,),
    "setApplicationName": (0,),
    "addItem": (0,),
    "setItemText": (1,),
    "information": (1, 2),
    "warning": (1, 2),
    "critical": (1, 2),
    "question": (1, 2),
    "getOpenFileName": (1, 3),
    "getSaveFileName": (1, 3),
    "getExistingDirectory": (1,),
}

#: Symbols, digits and punctuation carry no language.
NOT_TEXT = re.compile(r"^[\W\d_]*$")

#: Strings that are deliberately identical in every language.
ALLOWED = {
    "Detector Scenario Tool",
    # A hex identifier shown as an example of the expected format.
    "0x0FFF",
}


def _findings() -> list[str]:
    found: list[str] = []

    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            positions = DISPLAY_ARGUMENTS.get(name)
            if positions is None:
                continue

            for position in positions:
                if position >= len(node.args):
                    continue
                argument = node.args[position]
                if not isinstance(argument, ast.Constant):
                    continue
                if not isinstance(argument.value, str):
                    continue

                value = argument.value
                if not value or NOT_TEXT.match(value) or value in ALLOWED:
                    continue

                found.append(
                    f"{path.relative_to(SRC)}:{node.lineno} {name}(…{value!r}…)"
                )

    return found


def test_no_hardcoded_user_visible_text():
    findings = _findings()
    assert not findings, "wrap these in tr():\n  " + "\n  ".join(findings)


def test_the_scanner_can_actually_find_something(tmp_path):
    """Guard against the scan silently matching nothing after a refactor."""
    sample = tmp_path / "sample.py"
    sample.write_text('widget.setText("Hello")\n', encoding="utf-8")

    tree = ast.parse(sample.read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert calls and getattr(calls[0].func, "attr", None) in DISPLAY_ARGUMENTS


@pytest.mark.parametrize("path", sorted(SRC.rglob("*.py")), ids=lambda p: p.name)
def test_module_parses(path):
    """Cheap syntax check, and makes the scan above trustworthy."""
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
