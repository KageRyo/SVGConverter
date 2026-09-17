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
                "input",
                "no_input_selected",
                "selected_file",
                "selected_files",
                "selected_folder",
                "mode",
                "embed_mode",
                "vectorize_mode",
                "embed_mode_hint",
                "vectorize_mode_hint",
                "output_directory",
                "browse",
                "output_directory_hint",
                "output_same_as_source",
                "output_custom",
                "advanced_settings",
                "general_options",
                "overwrite",
                "recursive",
                "embed_options",
                "max_width",
                "max_height",
                "jpeg_quality",
                "png_compress_level",
                "optimize_png",
                "embed_options_hint",
                "vectorize_options",
                "color_mode",
                "hierarchical",
                "curve_mode",
                "filter_speckle",
                "color_precision",
                "layer_difference",
                "path_precision",
                "vectorize_options_hint",
                "invalid_options_title",
                "invalid_options",
                "select_files",
                "select_folder",
                "convert",
                "cancel",
                "ready",
                "starting",
                "progress",
                "cancelling",
                "done",
                "cancelled",
                "errors_title",
                "error",
                "result_success",
                "result_partial",
                "result_skipped",
                "result_cancelled",
                "result_failed",
                "result_counts",
                "result_single_size",
                "result_batch_size",
                "result_embedded_size",
                "result_output_same_as_source",
                "result_output_custom",
                "result_no_output",
                "result_failures",
                "open_output_folder",
                "convert_more",
            }
        )
    }
    assert locale_for_display_name("English", translations) == "en_US"
    assert locale_for_display_name("日本語", translations) == "ja_JP"


def test_unknown_locale_and_display_name_fall_back_to_default() -> None:
    translations = load_translations()

    assert locale_for_display_name("unknown", translations) == DEFAULT_LOCALE
    assert translation_for("unknown", translations) == translations[DEFAULT_LOCALE]
