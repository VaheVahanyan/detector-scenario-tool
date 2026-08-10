"""КУ / КТ / ТС must never reach the user as the raw internal code.

`KU` / `KT` / `TS` are transliterated Russian abbreviations kept as serialisation codes. In English
they mean nothing, so every display site goes through `utils.labels`.
"""

from __future__ import annotations

import pytest

from detector_scenario_tool.i18n import set_language, tr
from detector_scenario_tool.i18n.manager import _TRANSLATIONS
from detector_scenario_tool.utils.labels import (
    CATEGORY_CODES,
    category_long,
    category_short,
    message_label,
    message_label_from_ref,
)


@pytest.fixture(autouse=True)
def restore_language():
    yield
    set_language("ru")


class TestCategoryLabels:
    def test_russian_abbreviations(self):
        set_language("ru")
        assert category_short("KU") == "КУ"
        assert category_short("KT") == "КТ"
        assert category_short("TS") == "ТС"

    def test_english_abbreviations_are_not_transliterations(self):
        set_language("en")
        assert category_short("KU") == "CC"
        assert category_short("KT") == "TC"
        assert category_short("TS") == "TM"

    def test_english_long_forms_spell_out_the_meaning(self):
        set_language("en")
        assert category_long("KU") == "control command"
        assert category_long("KT") == "telemetry command"
        assert category_long("TS") == "telemetry message"

    def test_unknown_code_passes_through(self):
        assert category_short("XX") == "XX"

    @pytest.mark.parametrize("code", CATEGORY_CODES)
    @pytest.mark.parametrize("language", ["ru", "en"])
    def test_every_category_has_both_forms(self, code, language):
        set_language(language)
        assert category_short(code) and category_short(code) != f"category.{code}.short"
        assert category_long(code) and category_long(code) != f"category.{code}.long"


class TestMessageLabel:
    def test_label_includes_the_hex_id_and_the_catalogue_name(self):
        set_language("ru")
        assert message_label("KU", 0x0003) == "КУ 0x0003 Включение режима наблюдений"

    def test_name_comes_from_the_catalogue_not_from_the_caller(self):
        """A `MessageRef` stores the name as it was when the step was created.

        Using that snapshot would freeze the label in whatever language was active back then, so
        the catalogue wins and the stored name is only a fallback.
        """
        set_language("en")
        assert message_label("KU", 0x0003, "Включение режима наблюдений") == (
            "CC 0x0003 Start observation mode"
        )

    def test_unknown_message_falls_back_to_the_supplied_name(self):
        """Keeps stale files and user-defined commands readable."""
        set_language("en")
        assert message_label("KU", 0x0F99, "Custom command") == "CC 0x0F99 Custom command"

    def test_unknown_message_without_a_name_shows_just_the_id(self):
        set_language("en")
        assert message_label("KU", 0x0F99) == "CC 0x0F99"

    def test_label_from_a_missing_reference(self):
        assert message_label_from_ref(None) == tr("label.no_message")

    def test_label_from_an_incomplete_reference(self):
        from detector_scenario_tool.domain.scenario import MessageRef

        assert message_label_from_ref(MessageRef(category="KU")) == tr("label.no_message")


class TestNoRawCodesInTranslations:
    """The literal strings KU/KT/TS must not appear in any user-visible text."""

    @pytest.mark.parametrize("language", ["ru", "en"])
    def test_no_bare_category_codes(self, language):
        offenders = {}
        for key, value in _TRANSLATIONS[language].items():
            if key.startswith("category."):
                continue
            for code in ("KU", "KT", "TS"):
                # Word-ish check: the code standing alone, not inside another word.
                if f" {code} " in f" {value} " or value.strip() == code:
                    offenders.setdefault(key, []).append(code)
        assert not offenders, f"raw category codes in {language}: {offenders}"

    @pytest.mark.parametrize("language", ["ru", "en"])
    def test_no_internal_step_kind_names(self, language):
        """`WAIT_FOR_TS`, `SEND_KU` and friends are code identifiers, not user-facing text."""
        offenders = {
            key: value
            for key, value in _TRANSLATIONS[language].items()
            if any(token in value for token in ("WAIT_FOR_TS", "SEND_KU", "SEND_KT", "WAIT_TIME"))
        }
        assert not offenders, f"internal identifiers in {language}: {offenders}"
