"""Native event-loop checks; enable explicitly on a real or virtual display."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from threading import Event
from time import monotonic
from xml.etree import ElementTree

import pytest
from PIL import Image, ImageDraw

import svgconverter.gui as gui_module
from svgconverter import InputPathError
from svgconverter.gui import SVGConverterApp

pytestmark = pytest.mark.skipif(
    os.environ.get("SVGCONVERTER_NATIVE_GUI") != "1",
    reason="Native Tk checks require SVGCONVERTER_NATIVE_GUI=1 and a display",
)


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Iterator[SVGConverterApp]:
    application = SVGConverterApp()
    callback_errors: list[BaseException] = []
    application.root.report_callback_exception = lambda _kind, error, _traceback: (
        callback_errors.append(error)
    )
    # Exercise the error state without opening a blocking OS modal dialog.
    monkeypatch.setattr(
        gui_module.messagebox, "showerror", lambda *args, **kwargs: None
    )
    application.root.update()
    try:
        yield application
    finally:
        application._cancel_event.set()
        if application._worker is not None:
            application._worker.join(timeout=5)
        for callback_id in application.root.tk.call("after", "info"):
            application.root.after_cancel(callback_id)
        application.root.destroy()
        assert not callback_errors, callback_errors


def wait_for(app: SVGConverterApp, condition: Callable[[], bool]) -> None:
    """Run real Tk callbacks until an observable state changes, with a deadline."""

    deadline = monotonic() + 10
    while not condition():
        app.root.update()
        if monotonic() >= deadline:
            pytest.fail(f"GUI did not settle: {app.status_var.get()}")
        Event().wait(0.005)
    app.root.update()


def logo(path: Path) -> Path:
    image = Image.new("RGB", (32, 32), "white")
    ImageDraw.Draw(image).rectangle((8, 8, 24, 24), fill="black")
    image.save(path)
    return path


@pytest.mark.parametrize("mode", ["embed", "vectorize"])
def test_native_conversion_completes_and_can_start_again(
    app: SVGConverterApp, tmp_path: Path, mode: str
) -> None:
    if mode == "vectorize":
        pytest.importorskip("vtracer")
    source = logo(tmp_path / "logo 空間.png")
    destination = tmp_path / "out"
    app._set_selected_inputs((str(source),), "files")
    app.mode_var.set(mode)
    app._update_option_state()
    app.output_dir_var.set(str(destination))
    if mode == "embed":
        app.max_width_var.set("8")

    app.convert_button.invoke()

    assert app._running
    assert app.files_button.instate(["disabled"])
    assert app.convert_button.instate(["disabled"])
    assert app.cancel_button.instate(["!disabled"])
    wait_for(app, lambda: not app._running)
    assert app._worker is None
    result = app._last_result
    assert result is not None
    assert (result.success_count, result.failure_count) == (1, 0)
    assert result.converted == (destination / "logo 空間.svg",)
    assert result.metrics[0].svg_bytes == result.converted[0].stat().st_size
    document = ElementTree.parse(result.converted[0]).getroot()
    if mode == "embed":
        assert document.get("width") == "8"
    else:
        assert document.findall("{http://www.w3.org/2000/svg}path")
    assert app._events.empty()
    assert app.cancel_button.instate(["disabled"])
    assert app.open_output_button.instate(["!disabled"])

    app.convert_more_button.invoke()

    assert app._last_result is None
    assert app._selected_input_paths == ()
    assert app.convert_button.instate(["disabled"])
    assert not app.result_frame.winfo_manager()
    # A second real operation also exercises the end of the previous poll loop.
    app._set_selected_inputs((str(source),), "files")
    app.convert_button.invoke()
    wait_for(app, lambda: not app._running)
    assert app._last_result is not None
    assert app._last_result.skipped_count == 1
    assert app._worker is None


def test_native_batch_preserves_skip_and_failure_details(
    app: SVGConverterApp, tmp_path: Path
) -> None:
    good = logo(tmp_path / "good.png")
    existing = logo(tmp_path / "existing.png")
    invalid = tmp_path / "broken.png"
    invalid.write_bytes(b"not an image")
    prior_output = existing.with_suffix(".svg")
    prior_output.write_text("original output", encoding="utf-8")
    app._set_selected_inputs(tuple(map(str, (good, existing, invalid))), "files")

    app.convert_button.invoke()
    wait_for(app, lambda: not app._running)

    result = app._last_result
    assert result is not None
    assert (result.success_count, result.skipped_count, result.failure_count) == (
        1,
        1,
        1,
    )
    assert app.result_title_var.get() == app._text["result_partial"]
    assert invalid.name in app.result_details_var.get()
    assert prior_output.read_text(encoding="utf-8") == "original output"
    assert not invalid.with_suffix(".svg").exists()
    assert app.files_button.instate(["!disabled"])
    assert app.convert_button.instate(["!disabled"])


def test_native_cancellation_stops_after_the_current_file(
    app: SVGConverterApp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources = (logo(tmp_path / "one.png"), logo(tmp_path / "two.png"))
    checkpoint = Event()
    release = Event()
    original_convert = gui_module.convert_paths

    def paused_convert(*args: object, **kwargs: object) -> object:
        progress_callback = kwargs["progress_callback"]

        def report_progress(progress: object) -> None:
            progress_callback(progress)
            checkpoint.set()
            if not release.wait(timeout=5):
                raise RuntimeError("Test did not release the conversion checkpoint")

        kwargs["progress_callback"] = report_progress
        return original_convert(*args, **kwargs)

    monkeypatch.setattr(gui_module, "convert_paths", paused_convert)
    app._set_selected_inputs(tuple(map(str, sources)), "files")
    try:
        app.convert_button.invoke()
        wait_for(app, lambda: checkpoint.is_set() and app.progress["value"] == 1)
        assert app.progress["maximum"] == 2

        app.cancel_button.invoke()

        assert app._cancel_event.is_set()
        assert app.cancel_button.instate(["disabled"])
        assert app.status_var.get() == app._text["cancelling"]
    finally:
        release.set()
    wait_for(app, lambda: not app._running)
    result = app._last_result
    assert result is not None
    assert result.cancelled
    assert result.success_count == 1
    assert sources[0].with_suffix(".svg").is_file()
    assert not sources[1].with_suffix(".svg").exists()
    assert app.result_title_var.get() == app._text["result_cancelled"]
    assert app._worker is None
    assert app._events.empty()


@pytest.mark.parametrize("error_type", [InputPathError, RuntimeError])
def test_native_worker_error_restores_editable_state(
    app: SVGConverterApp,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
) -> None:
    source = logo(tmp_path / "source.png")

    def fail_conversion(*args: object, **kwargs: object) -> object:
        raise error_type("conversion worker failed")

    monkeypatch.setattr(gui_module, "convert_paths", fail_conversion)
    app._set_selected_inputs((str(source),), "files")

    app.convert_button.invoke()
    wait_for(app, lambda: not app._running)

    assert app._worker is None
    assert app._last_result is None
    assert app.result_title_var.get() == app._text["result_failed"]
    assert app.result_summary_var.get() == "conversion worker failed"
    assert app.status_var.get() == app._text["error"]
    assert app.convert_button.instate(["!disabled"])
    assert app.max_width_entry.instate(["!disabled"])
    assert app.cancel_button.instate(["disabled"])
    assert app.open_output_button.instate(["disabled"])
    assert not source.with_suffix(".svg").exists()


def test_native_invalid_options_do_not_start_a_worker(
    app: SVGConverterApp, tmp_path: Path
) -> None:
    source = logo(tmp_path / "source.png")
    app._set_selected_inputs((str(source),), "files")
    app.max_width_var.set("not a width")

    app.convert_button.invoke()
    app.root.update()

    assert not app._running
    assert app._worker is None
    assert app._events.empty()
    assert app.status_var.get() == app._text["invalid_options"]
    assert app.max_width_entry.instate(["!disabled"])
    assert not source.with_suffix(".svg").exists()


def test_native_language_switch_preserves_running_and_completed_conversion(
    app: SVGConverterApp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = logo(tmp_path / "source.png")
    entered = Event()
    release = Event()
    original_convert = gui_module.convert_paths

    def paused_convert(*args: object, **kwargs: object) -> object:
        entered.set()
        if not release.wait(timeout=5):
            raise RuntimeError("Test did not release the conversion checkpoint")
        return original_convert(*args, **kwargs)

    monkeypatch.setattr(gui_module, "convert_paths", paused_convert)
    app._set_selected_inputs((str(source),), "files")
    selected_paths = app._selected_input_paths
    original_locale = app.locale
    target_locale = next(locale for locale in app.translations if locale != app.locale)
    try:
        app.convert_button.invoke()
        wait_for(app, entered.is_set)

        app.language_var.set(app.translations[target_locale]["name"])
        app.change_language(app.language_var)
        app.root.update()

        assert app.locale == target_locale
        assert app._running
        assert app.status_var.get() != app._text["ready"]
        assert app.convert_button.instate(["disabled"])
    finally:
        release.set()
    wait_for(app, lambda: not app._running)
    result = app._last_result
    assert result is not None
    assert app._selected_input_paths == selected_paths
    assert app.result_title_var.get() == app._text["result_success"]
    assert app.result_summary_var.get() == app._text["result_counts"].format(
        converted=1, skipped=0, failed=0
    )

    app.change_language(app.translations[original_locale]["name"])
    app.root.update()

    assert app.locale == original_locale
    assert app._last_result is result
    assert app.result_title_var.get() == app._text["result_success"]
    assert app.open_output_button.instate(["!disabled"])
