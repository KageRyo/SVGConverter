from __future__ import annotations

from pathlib import Path
from queue import Queue
from threading import Event

import pytest

import svgconverter.gui as gui_module
from svgconverter import (
    BatchResult,
    ConversionError,
    ConversionFailure,
    EmbedOptions,
    VectorizeOptions,
)
from svgconverter.gui import (
    GuiConversionOptions,
    SVGConverterApp,
    build_embed_options,
    build_vectorize_options,
    format_failure_details,
)


class FakeVar:
    def __init__(self, value: object) -> None:
        self.value = value

    def get(self) -> object:
        return self.value


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
