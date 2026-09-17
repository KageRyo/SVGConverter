from __future__ import annotations

from pathlib import Path
from queue import Queue
from threading import Event
from unittest.mock import Mock

import pytest

import svgconverter.gui as gui_module
from svgconverter import (
    BatchResult,
    ConversionError,
    ConversionFailure,
    ConversionMetrics,
    ConversionSkip,
    EmbedOptions,
    VectorizeOptions,
)
from svgconverter.gui import (
    GuiConversionOptions,
    SVGConverterApp,
    build_embed_options,
    build_vectorize_options,
    format_byte_size,
    format_failure_details,
    format_result_counts,
    format_result_metrics,
    result_status_key,
)


class FakeVar:
    def __init__(self, value: object) -> None:
        self.value = value

    def get(self) -> object:
        return self.value

    def set(self, value: object) -> None:
        self.value = value


def fake_app_for_options(**values: object) -> SVGConverterApp:
    app = object.__new__(SVGConverterApp)
    for name, value in values.items():
        setattr(app, name, FakeVar(value))
    return app


def test_format_failure_details_lists_each_failed_input() -> None:
    result = BatchResult(
        converted=(),
        skipped=(),
        failed=(
            ConversionFailure(Path("broken.png"), ConversionError("not readable")),
            ConversionFailure(Path("unsupported.gif"), ConversionError("unsupported")),
        ),
    )

    assert format_failure_details(result) == (
        "broken.png: not readable\nunsupported.gif: unsupported"
    )


def test_result_status_key_distinguishes_completion_outcomes() -> None:
    skipped = ConversionSkip(Path("existing.png"), Path("existing.svg"), "exists")
    failure = ConversionFailure(Path("broken.png"), ConversionError("not readable"))

    assert result_status_key(
        BatchResult(converted=(Path("photo.svg"),), failed=())
    ) == ("result_success")
    assert result_status_key(
        BatchResult(converted=(), failed=(), skipped=(skipped,))
    ) == ("result_skipped")
    assert (
        result_status_key(
            BatchResult(converted=(Path("photo.svg"),), failed=(failure,))
        )
        == "result_partial"
    )
    assert result_status_key(BatchResult(converted=(), failed=(failure,))) == (
        "result_failed"
    )
    assert (
        result_status_key(
            BatchResult(converted=(Path("photo.svg"),), failed=(), cancelled=True)
        )
        == "result_cancelled"
    )


def test_result_counts_and_metrics_are_readable() -> None:
    metric = ConversionMetrics(
        input_path=Path("photo.jpg"),
        output_path=Path("photo.svg"),
        input_bytes=2048,
        svg_bytes=4096,
        embedded_raster_bytes=2048,
    )
    result = BatchResult(converted=(Path("photo.svg"),), failed=(), metrics=(metric,))
    text = {
        "result_counts": "{converted} converted; {skipped} skipped; {failed} failed.",
        "result_single_size": "{input} → {output}: {input_size} → {svg_size}",
        "result_batch_size": "{input_size} input → {svg_size} SVG",
        "result_embedded_size": "Embedded raster: {size}",
    }

    assert format_byte_size(2048) == "2.00 KB"
    assert format_result_counts(result, text) == "1 converted; 0 skipped; 0 failed."
    assert format_result_metrics(result, text) == (
        "photo.jpg → photo.svg: 2.00 KB → 4.00 KB\nEmbedded raster: 2.00 KB"
    )


def test_result_feedback_renders_output_location_and_folder_action(
    tmp_path: Path,
) -> None:
    metric = ConversionMetrics(
        input_path=Path("photo.jpg"),
        output_path=tmp_path / "photo.svg",
        input_bytes=2048,
        svg_bytes=4096,
        embedded_raster_bytes=2048,
    )
    result = BatchResult(
        converted=(tmp_path / "photo.svg",), failed=(), metrics=(metric,)
    )
    app = object.__new__(SVGConverterApp)
    app.locale = "en_US"
    app.translations = {
        "en_US": {
            "result_success": "Conversion complete",
            "result_counts": (
                "{converted} converted; {skipped} skipped; {failed} failed."
            ),
            "result_single_size": "{input} → {output}: {input_size} → {svg_size}",
            "result_batch_size": "{input_size} input → {svg_size} SVG",
            "result_embedded_size": "Embedded raster: {size}",
            "result_output_custom": "Output: {path}",
            "result_output_same_as_source": "Output: beside each source image",
            "result_no_output": "No output files were created.",
            "result_failures": "Failed files:\n{details}",
        }
    }
    app._last_conversion_options = GuiConversionOptions(
        mode="embed",
        output_dir=str(tmp_path),
        overwrite=False,
        recursive=False,
        embed_options=None,
        vectorize_options=None,
    )
    app.result_title_var = FakeVar("")
    app.result_summary_var = FakeVar("")
    app.result_metrics_var = FakeVar("")
    app.result_output_var = FakeVar("")
    app.result_details_var = FakeVar("")
    app.result_frame = Mock()
    app.open_output_button = Mock()
    app.language_menu = object()

    app._render_result_feedback(result)

    assert app.result_title_var.get() == "Conversion complete"
    assert app.result_summary_var.get() == "1 converted; 0 skipped; 0 failed."
    assert app.result_output_var.get() == f"Output: {tmp_path}"
    assert "photo.jpg" in app.result_metrics_var.get()
    app.open_output_button.configure.assert_called_once_with(state=gui_module.tk.NORMAL)
    app.result_frame.pack.assert_called_once_with(
        fill=gui_module.tk.X, pady=(12, 0), before=app.language_menu
    )


def test_reset_for_new_conversion_returns_to_ready_state() -> None:
    app = object.__new__(SVGConverterApp)
    app._running = False
    app._selected_input_paths = ("photo.png",)
    app._selected_input_kind = "files"
    app._last_result = Mock()
    app._last_conversion_options = Mock()
    app._result_output_folder = Path("/tmp/svg-output")
    app.result_frame = Mock()
    app.progress = Mock()
    app.input_summary_var = FakeVar("Selected file: photo.png")
    app.status_var = FakeVar("Conversion complete")
    app.locale = "en_US"
    app.translations = {
        "en_US": {
            "no_input_selected": "No files or folder selected.",
            "ready": "Select files or a folder to start converting.",
        }
    }
    app._update_action_state = Mock()

    reset_for_new_conversion = getattr(app, "reset_for_new_conversion", None)

    assert callable(reset_for_new_conversion)
    reset_for_new_conversion()

    assert app._selected_input_paths == ()
    assert app._selected_input_kind is None
    assert app._last_result is None
    assert app._last_conversion_options is None
    assert app._result_output_folder is None
    assert app.input_summary_var.get() == "No files or folder selected."
    assert app.status_var.get() == "Select files or a folder to start converting."
    app.result_frame.pack_forget.assert_called_once_with()
    app.progress.configure.assert_called_once_with(value=0, maximum=1)


def test_select_files_records_selection_without_starting_conversion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = object.__new__(SVGConverterApp)
    app.root = object()
    app.locale = "en_US"
    app.translations = {"en_US": {"select_files": "Select Files"}}
    app._set_selected_inputs = Mock()
    app._start_conversion = Mock()
    selected_files = ("photo.png", "logo.jpg")
    monkeypatch.setattr(
        gui_module.filedialog,
        "askopenfilenames",
        lambda **_: selected_files,
    )

    app.select_files()

    app._set_selected_inputs.assert_called_once_with(selected_files, "files")
    app._start_conversion.assert_not_called()


def test_select_folder_records_selection_without_starting_conversion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = object.__new__(SVGConverterApp)
    app.root = object()
    app.locale = "en_US"
    app.translations = {"en_US": {"select_folder": "Select Folder"}}
    app._set_selected_inputs = Mock()
    app._start_conversion = Mock()
    monkeypatch.setattr(
        gui_module.filedialog,
        "askdirectory",
        lambda **_: "/tmp/images",
    )

    app.select_folder()

    app._set_selected_inputs.assert_called_once_with(("/tmp/images",), "folder")
    app._start_conversion.assert_not_called()


def test_convert_selected_starts_conversion_for_recorded_inputs() -> None:
    app = object.__new__(SVGConverterApp)
    app._selected_input_paths = ("photo.png", "logo.jpg")
    app._start_conversion = Mock()
    convert_selected = getattr(app, "convert_selected", None)

    assert callable(convert_selected)
    convert_selected()

    app._start_conversion.assert_called_once_with(app._selected_input_paths)


def test_input_summary_describes_multiple_selected_files() -> None:
    app = object.__new__(SVGConverterApp)
    app._selected_input_paths = ("photo.png", "logo.jpg")
    app._selected_input_kind = "files"
    app.locale = "en_US"
    app.translations = {
        "en_US": {
            "no_input_selected": "No input selected",
            "selected_file": "Selected file: {file}",
            "selected_files": "{count} files selected",
            "selected_folder": "Selected folder: {folder}",
        }
    }
    input_summary_text = getattr(app, "_input_summary_text", None)

    assert callable(input_summary_text)
    assert input_summary_text() == "2 files selected"


def test_mode_hint_explains_the_selected_conversion_outcome() -> None:
    app = object.__new__(SVGConverterApp)
    app.locale = "en_US"
    app.translations = {
        "en_US": {
            "embed_mode_hint": "Keep the original appearance.",
            "vectorize_mode_hint": "Create editable vector paths.",
        }
    }
    app.mode_var = FakeVar("embed")
    mode_hint_text = getattr(app, "_mode_hint_text", None)

    assert callable(mode_hint_text)
    assert mode_hint_text() == "Keep the original appearance."

    app.mode_var.set("vectorize")

    assert mode_hint_text() == "Create editable vector paths."


def test_selected_inputs_are_converted_only_after_explicit_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = object.__new__(SVGConverterApp)
    app.root = object()
    app.locale = "en_US"
    app.translations = {"en_US": {"select_files": "Select Files"}}
    app._selected_input_paths = ()
    app._selected_input_kind = None
    app._refresh_input_summary = Mock()
    app._update_action_state = Mock()
    app._start_conversion = Mock()
    selected_files = ("photo.png",)
    monkeypatch.setattr(
        gui_module.filedialog,
        "askopenfilenames",
        lambda **_: selected_files,
    )

    app.select_files()

    app._start_conversion.assert_not_called()
    app.convert_selected()

    app._start_conversion.assert_called_once_with(selected_files)


def test_output_summary_makes_default_and_custom_locations_explicit() -> None:
    app = object.__new__(SVGConverterApp)
    app.locale = "en_US"
    app.translations = {
        "en_US": {
            "output_same_as_source": "Save beside each source image",
            "output_custom": "Save to: {path}",
        }
    }
    app.output_dir_var = FakeVar("")

    assert app._output_summary_text() == "Save beside each source image"

    app.output_dir_var = FakeVar("  /tmp/svg-output  ")

    assert app._output_summary_text() == "Save to: /tmp/svg-output"


def test_convert_button_is_disabled_without_inputs_and_enabled_after_selection() -> (
    None
):
    app = object.__new__(SVGConverterApp)
    app._running = False
    app._selected_input_paths = ()
    app.files_button = Mock()
    app.folder_button = Mock()
    app.convert_button = Mock()

    app._update_action_state()

    app.convert_button.configure.assert_called_once_with(state=gui_module.tk.DISABLED)

    app.convert_button.reset_mock()
    app._selected_input_paths = ("photo.png",)
    app._update_action_state()

    app.convert_button.configure.assert_called_once_with(state=gui_module.tk.NORMAL)


def test_advanced_settings_toggle_changes_visibility() -> None:
    app = object.__new__(SVGConverterApp)
    app.advanced_expanded = FakeVar(False)
    app.advanced_frame = Mock()
    toggle_advanced_settings = getattr(app, "toggle_advanced_settings", None)

    assert callable(toggle_advanced_settings)

    toggle_advanced_settings()

    assert app.advanced_expanded.get() is True
    app.advanced_frame.pack.assert_called_once_with(fill=gui_module.tk.X, pady=(10, 0))

    toggle_advanced_settings()

    assert app.advanced_expanded.get() is False
    app.advanced_frame.pack_forget.assert_called_once_with()


def test_toggling_advanced_settings_preserves_option_values() -> None:
    app = fake_app_for_options(
        mode_var="embed",
        output_dir_var="/tmp/svg-output",
        overwrite_var=True,
        recursive_var=True,
        max_width_var="1200",
        max_height_var="800",
        jpeg_quality_var="85",
        png_compress_level_var="9",
        optimize_png_var=True,
        color_mode_var="color",
        hierarchical_var="stacked",
        curve_mode_var="spline",
        filter_speckle_var="3",
        color_precision_var="6",
        layer_difference_var="10",
        path_precision_var="8",
    )
    app.advanced_expanded = FakeVar(False)
    app.advanced_frame = Mock()
    toggle_advanced_settings = getattr(app, "toggle_advanced_settings", None)

    assert callable(toggle_advanced_settings)
    before = app._build_conversion_options()

    toggle_advanced_settings()
    toggle_advanced_settings()

    assert app._build_conversion_options() == before


def test_build_embed_options_maps_fields_and_keeps_defaults_unset() -> None:
    assert build_embed_options() is None

    options = build_embed_options(
        max_width="1600",
        max_height="",
        jpeg_quality="82",
        png_compress_level=None,
        optimize_png=False,
    )

    assert options == EmbedOptions(max_width=1600, jpeg_quality=82)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("max_width", "Maximum width must be a whole number"),
        ("jpeg_quality", "JPEG quality must be a whole number"),
    ],
)
def test_build_embed_options_rejects_non_integer_fields(
    field: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        build_embed_options(**{field: "not-a-number"})


def test_build_conversion_options_maps_embed_mode_controls() -> None:
    app = fake_app_for_options(
        mode_var="embed",
        output_dir_var="  /tmp/svg-output  ",
        overwrite_var=True,
        recursive_var=True,
        max_width_var="1200",
        max_height_var="800",
        jpeg_quality_var="85",
        png_compress_level_var="9",
        optimize_png_var=True,
        color_mode_var="color",
        hierarchical_var="stacked",
        curve_mode_var="spline",
        filter_speckle_var="",
        color_precision_var="",
        layer_difference_var="",
        path_precision_var="",
    )

    options = app._build_conversion_options()

    assert options == GuiConversionOptions(
        mode="embed",
        output_dir="/tmp/svg-output",
        overwrite=True,
        recursive=True,
        embed_options=EmbedOptions(
            max_width=1200,
            max_height=800,
            jpeg_quality=85,
            png_compress_level=9,
            optimize_png=True,
        ),
        vectorize_options=None,
    )


def test_build_conversion_options_maps_vectorize_mode_controls() -> None:
    app = fake_app_for_options(
        mode_var="vectorize",
        output_dir_var="",
        overwrite_var=False,
        recursive_var=False,
        max_width_var="100",
        max_height_var="100",
        jpeg_quality_var="80",
        png_compress_level_var="6",
        optimize_png_var=True,
        color_mode_var="binary",
        hierarchical_var="cutout",
        curve_mode_var="polygon",
        filter_speckle_var="4",
        color_precision_var="6",
        layer_difference_var="12",
        path_precision_var="3",
    )

    options = app._build_conversion_options()

    assert options == GuiConversionOptions(
        mode="vectorize",
        output_dir=None,
        overwrite=False,
        recursive=False,
        embed_options=None,
        vectorize_options=VectorizeOptions(
            color_mode="binary",
            hierarchical="cutout",
            curve_mode="polygon",
            filter_speckle=4,
            color_precision=6,
            layer_difference=12,
            path_precision=3,
        ),
    )


def test_build_vectorize_options_rejects_unknown_choice() -> None:
    with pytest.raises(ValueError, match="Color mode must be one of"):
        build_vectorize_options(color_mode="posterize")


def test_run_conversion_forwards_the_settings_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = object.__new__(SVGConverterApp)
    app._events = Queue()
    app._cancel_event = Event()
    app._report_progress = lambda progress: None
    result = BatchResult(converted=(), failed=())
    captured: dict[str, object] = {}

    def fake_convert_paths(input_paths: object, **kwargs: object) -> BatchResult:
        captured["input_paths"] = input_paths
        captured.update(kwargs)
        return result

    monkeypatch.setattr(gui_module, "convert_paths", fake_convert_paths)
    options = GuiConversionOptions(
        mode="vectorize",
        output_dir="/tmp/output",
        overwrite=True,
        recursive=True,
        embed_options=None,
        vectorize_options=VectorizeOptions(color_mode="binary"),
    )

    app._run_conversion(("logo.png",), options)

    assert captured == {
        "input_paths": ("logo.png",),
        "output_dir": "/tmp/output",
        "overwrite": True,
        "recursive": True,
        "mode": "vectorize",
        "vectorize_options": VectorizeOptions(color_mode="binary"),
        "embed_options": None,
        "progress_callback": app._report_progress,
        "should_cancel": app._cancel_event.is_set,
    }
    assert app._events.get_nowait() == ("done", result)
