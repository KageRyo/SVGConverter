from __future__ import annotations

from pathlib import Path
from queue import Queue
from threading import Event
from unittest.mock import Mock

import pytest

import svgconverter.gui as gui_module
from svgconverter.gui import GuiConversionOptions, SVGConverterApp
from svgconverter.i18n import load_translations
from svgconverter.models import EmbedOptions


class Value:
    def __init__(self, value: object):
        self.value = value

    def get(self):
        return self.value

    def set(self, value: object):
        self.value = value


def make_app() -> SVGConverterApp:
    app = object.__new__(SVGConverterApp)
    app.root = Mock()
    app._events = Queue()
    app._cancel_event = Event()
    app._running = False
    app._worker = None
    app._closing = False
    app._preview_active = False
    app._selected_input_paths = ("source.png",)
    app._selected_input_kind = "files"
    app.locale = "en_US"
    app.translations = load_translations()
    app.status_var = Value("")
    app.progress = Mock()
    app._set_running = Mock()
    app._build_conversion_options = Mock(
        return_value=GuiConversionOptions(
            mode="embed",
            output_dir="ignored-output",
            overwrite=True,
            recursive=True,
            embed_options=EmbedOptions(max_width=100),
            vectorize_options=None,
        )
    )
    return app


def test_preview_starts_worker_with_captured_settings_and_no_output_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = make_app()
    thread = Mock()
    monkeypatch.setattr(gui_module, "Thread", Mock(return_value=thread))
    app._run_conversion = Mock()

    app.preview_selected()

    captured = gui_module.Thread.call_args.kwargs
    assert captured["target"] == app._run_preview
    assert captured["args"] == (
        "source.png",
        app._build_conversion_options.return_value,
    )
    thread.start.assert_called_once()
    app._set_running.assert_called_once_with(True)
    app._run_conversion.assert_not_called()
    assert app._preview_active is True
    assert app.status_var.get() == app._text["preview_starting"]


@pytest.mark.parametrize(
    "kind,inputs,running",
    [
        ("folder", ("images",), False),
        ("files", ("first.png", "second.png"), False),
        ("files", (), False),
        ("files", ("source.png",), True),
    ],
)
def test_preview_rejects_non_single_selection_and_active_work(
    monkeypatch: pytest.MonkeyPatch, kind: str, inputs: tuple[str, ...], running: bool
) -> None:
    app = make_app()
    app._selected_input_kind = kind
    app._selected_input_paths = inputs
    app._running = running
    thread = Mock()
    monkeypatch.setattr(gui_module, "Thread", thread)

    app.preview_selected()

    thread.assert_not_called()


def test_preview_worker_passes_snapshot_and_only_queues_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = make_app()
    options = app._build_conversion_options()
    result = object()
    preview = Mock(return_value=result)
    monkeypatch.setattr(gui_module, "create_preview", preview)

    app._run_preview("source.png", options)

    preview.assert_called_once_with(
        "source.png",
        mode="embed",
        embed_options=options.embed_options,
        vectorize_options=None,
        should_cancel=app._cancel_event.is_set,
    )
    assert app._events.get_nowait() == ("preview_done", result)
    app.root.assert_not_called()


def test_cancelled_preview_result_is_discarded_without_opening_window() -> None:
    from svgconverter.preview import PreviewResult

    app = make_app()
    app._cancel_event.set()
    app._open_preview_window = Mock()
    result = PreviewResult(
        Path("source.png"), "embed", b"", b"", (2, 2), (2, 2), 10, 20, 10, False
    )

    app._show_preview_result(result)

    app._open_preview_window.assert_not_called()
    app._set_running.assert_called_once_with(False)
    assert app.status_var.get() == app._text["preview_cancelled"]


def test_closing_gui_waits_for_worker_cleanup_without_blocking_tk() -> None:
    app = make_app()
    app._running = True
    app._worker = Mock()
    app._worker.is_alive.return_value = True

    app.close()

    assert app._closing is True
    assert app._cancel_event.is_set()
    app.root.destroy.assert_not_called()
    app.root.after.assert_called_once()
    app._worker.is_alive.return_value = False

    app._finish_close()

    app.root.destroy.assert_called_once()


def test_closed_gui_does_not_consume_or_display_worker_events() -> None:
    app = make_app()
    app._closing = True
    app._events.put(("preview_done", object()))
    app._show_preview_result = Mock()

    app._poll_events()

    assert not app._events.empty()
    app._show_preview_result.assert_not_called()
    app.root.after.assert_not_called()


@pytest.mark.parametrize("failure", ["renderer", "backend", "cancelled", "unexpected"])
def test_preview_worker_errors_are_localized_and_restore_controls(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    from svgconverter import VectorizationDependencyError
    from svgconverter.preview import (
        PreviewCancelled,
        PreviewDependencyError,
        PreviewError,
    )

    app = make_app()
    options = app._build_conversion_options()
    app._preview_active = True
    if failure == "renderer":
        error = PreviewDependencyError("renderer is absent")
        key = "preview_missing_renderer"
    elif failure == "backend":
        error = PreviewError("backend is absent")
        error.__cause__ = VectorizationDependencyError("backend is absent")
        key = "preview_missing_vectorize"
    elif failure == "cancelled":
        error = PreviewCancelled("cancelled")
        key = "preview_cancelled"
    else:
        error = PreviewError("cannot render")
        key = "preview_error"
    monkeypatch.setattr(gui_module, "create_preview", Mock(side_effect=error))
    dialog = Mock()
    monkeypatch.setattr(gui_module.messagebox, "showerror", dialog)

    app._run_preview("source.png", options)
    app._poll_events()

    assert app.status_var.get() == app._text[key].format(error=error)
    assert app._preview_active is False
    app._set_running.assert_called_once_with(False)
    if failure == "cancelled":
        dialog.assert_not_called()
    else:
        dialog.assert_called_once()


def test_invalid_preview_options_do_not_start_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = make_app()
    app._build_conversion_options.side_effect = ValueError("invalid size")
    thread = Mock()
    monkeypatch.setattr(gui_module, "Thread", thread)
    monkeypatch.setattr(gui_module.messagebox, "showerror", Mock())

    app.preview_selected()

    thread.assert_not_called()
    assert app.status_var.get() == app._text["invalid_options"]
