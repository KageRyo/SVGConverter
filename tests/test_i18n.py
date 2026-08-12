from __future__ import annotations

from svgconverter.i18n import (
    DEFAULT_LOCALE,
    load_translations,
    locale_for_display_name,
    translation_for,
)


def test_bundled_translations_have_all_supported_locales() -> None:
    translations = load_translations()

    assert set(translations) == {"zh_TW", "en_US", "ja_JP"}
    assert {frozenset(text) for text in translations.values()} == {
        frozenset(
            {
                "name",
                "select_files",
                "select_folder",
                "cancel",
                "ready",
                "starting",
                "progress",
                "cancelling",
                "done",
                "cancelled",
                "errors_title",
                "error",
            }
        )
    }
    assert locale_for_display_name("English", translations) == "en_US"
    assert locale_for_display_name("日本語", translations) == "ja_JP"


def test_unknown_locale_and_display_name_fall_back_to_default() -> None:
    translations = load_translations()

    assert locale_for_display_name("unknown", translations) == DEFAULT_LOCALE
    assert translation_for("unknown", translations) == translations[DEFAULT_LOCALE]
