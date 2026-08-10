"""Translation dictionaries must stay in step with each other and with the code.

Adding a key to only one language is invisible at runtime — `tr()` silently falls back to English
and then to the raw key, so the UI just shows `inspector.field.foo`. These tests make that a
build failure instead.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from detector_scenario_tool.i18n.manager import _TRANSLATIONS, available_languages, tr

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "detector_scenario_tool"
PLACEHOLDER = re.compile(r"\{(\w+)")

LANGUAGES = sorted(_TRANSLATIONS)


def test_expected_languages_are_present():
    assert set(available_languages()) == {"ru", "en"}


def test_language_key_sets_are_identical():
    reference = set(_TRANSLATIONS["en"])
    for language in LANGUAGES:
        missing = reference - set(_TRANSLATIONS[language])
        extra = set(_TRANSLATIONS[language]) - reference
        assert not missing, f"{language} is missing: {sorted(missing)}"
        assert not extra, f"{language} has keys English does not: {sorted(extra)}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_empty_translations(language):
    empty = [key for key, value in _TRANSLATIONS[language].items() if not value.strip()]
    assert not empty, f"empty {language} strings: {empty}"


def test_placeholders_match_across_languages():
    for key, english in _TRANSLATIONS["en"].items():
        expected = set(PLACEHOLDER.findall(english))
        for language in LANGUAGES:
            actual = set(PLACEHOLDER.findall(_TRANSLATIONS[language][key]))
            assert actual == expected, f"{key} in {language}: {actual} != {expected}"


def _tr_keys_used_in_source() -> dict[str, set[Path]]:
    """Every tr("literal") call in the package, mapped to the files that use it."""
    used: dict[str, set[Path]] = {}
    for path in SRC_ROOT.rglob("*.py"):
        if path.name == "manager.py" and path.parent.name == "i18n":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name != "tr" or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                used.setdefault(first.value, set()).add(path.relative_to(SRC_ROOT))
    return used


def test_every_key_used_in_code_is_translated():
    used = _tr_keys_used_in_source()
    assert used, "AST scan found no tr() calls — the scanner is broken"

    missing = {
        key: sorted(str(p) for p in paths)
        for key, paths in used.items()
        if key not in _TRANSLATIONS["en"]
    }
    assert not missing, f"untranslated keys used in code: {missing}"


def test_translation_lookup_falls_back_to_the_key():
    assert tr("no.such.key.exists") == "no.such.key.exists"


def test_formatting_arguments_are_applied():
    key, template = next(
        (k, v) for k, v in _TRANSLATIONS["en"].items() if PLACEHOLDER.search(v)
    )
    names = PLACEHOLDER.findall(template)
    rendered = tr(key, **{name: "X" for name in names})
    assert "{" not in rendered
