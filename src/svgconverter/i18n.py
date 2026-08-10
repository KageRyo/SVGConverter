"""Package-safe localization helpers for the Tkinter interface."""

from __future__ import annotations

import json
from importlib import resources

DEFAULT_LOCALE = "zh_TW"


def load_translations() -> dict[str, dict[str, str]]:
    """Load bundled translations without relying on the current directory."""

    resource = resources.files("svgconverter.resources").joinpath("languages.json")
    with resource.open("r", encoding="utf-8") as translation_file:
        translations: dict[str, dict[str, str]] = json.load(translation_file)
    return translations


def locale_for_display_name(
    display_name: str, translations: dict[str, dict[str, str]]
) -> str:
    """Return the locale key represented by a language menu label.

    Unknown labels use Traditional Chinese, the package's default locale.
    """

    for locale, text in translations.items():
        if text.get("name") == display_name:
            return locale
    return (
        DEFAULT_LOCALE if DEFAULT_LOCALE in translations else next(iter(translations))
    )


def translation_for(
    locale: str, translations: dict[str, dict[str, str]]
) -> dict[str, str]:
    """Return translations for ``locale`` with a safe fallback."""

    return translations.get(
        locale, translations.get(DEFAULT_LOCALE, next(iter(translations.values())))
    )
