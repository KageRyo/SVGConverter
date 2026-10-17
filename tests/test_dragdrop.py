import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

import svgconverter.dragdrop as dragdrop_module
from svgconverter.gui import SVGConverterApp
from svgconverter.i18n import load_translations


class Value:
    def __init__(self, value: object) -> None:
        self.value = value

    def set(self, value: object) -> None:
        self.value = value

    def get(self) -> object:
        return self.value


def app_for_drop() -> SVGConverterApp:
    app = object.__new__(SVGConverterApp)
    app.root = tk.Tcl()
    app.locale = "en_US"
    app.translations = load_translations()
    app._running = False
    app._selected_input_paths = ()
    app._selected_input_kind = None
    app.status_var = Value("")
    app.input_summary_var = Value("")
    app._hide_result_feedback = Mock()
    app._update_action_state = Mock()
    app._start_conversion = Mock()
    return app


def test_drop_parses_tcl_paths_deduplicates_and_selects_without_converting(
    tmp_path: Path,
) -> None:
    app = app_for_drop()
    source = tmp_path / "image spaces 漢字.png"
    Image.new("RGB", (2, 2)).save(source)
    folder = tmp_path / "folder spaces 日本語"
    folder.mkdir()
    event = SimpleNamespace(
        data=app.root.tk.call("list", str(source), str(folder), str(source))
    )
    assert app._on_drop(event) == "copy"
    assert app._selected_input_paths == (str(source), str(folder))
    assert "2" in app.input_summary_var.get()
    assert app._selected_input_kind == "mixed"
    app._start_conversion.assert_not_called()


def test_partial_invalid_drop_reports_items_and_keeps_valid_selection(
    tmp_path: Path,
) -> None:
    app = app_for_drop()
    source = tmp_path / "valid.PNG"
    Image.new("RGB", (2, 2)).save(source)
    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("notes")
    missing = tmp_path / "missing.png"
    event = SimpleNamespace(
        data=app.root.tk.call("list", str(source), str(unsupported), str(missing))
    )
    assert app._on_drop(event) == "copy"
    assert app._selected_input_paths == (str(source),)
    assert "notes.txt" in app.status_var.get()
    assert "missing.png" in app.status_var.get()
    app._start_conversion.assert_not_called()


def test_invalid_and_busy_drops_preserve_selection(tmp_path: Path) -> None:
    app = app_for_drop()
    app._selected_input_paths = ("existing.png",)
    assert app._on_drop(SimpleNamespace(data="{")) == "refuse_drop"
    assert app._selected_input_paths == ("existing.png",)
    app._running = True
    source = tmp_path / "valid.png"
    Image.new("RGB", (2, 2)).save(source)
    assert app._on_drop(SimpleNamespace(data=str(source))) == "refuse_drop"
    assert app._selected_input_paths == ("existing.png",)


def test_gui_root_stays_usable_without_optional_drop_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interpreter = tk.Tcl()

    def missing_backend(_name: str) -> object:
        raise ModuleNotFoundError("No module named 'tkinterdnd2'")

    monkeypatch.setattr(dragdrop_module.importlib, "import_module", missing_backend)
    monkeypatch.setattr(dragdrop_module.tk, "Tk", lambda: interpreter)

    root, available = dragdrop_module.create_drop_root()

    assert available is False
    root.tk.call("set", "application_state", "ready")
    assert root.tk.call("set", "application_state") == "ready"


@pytest.mark.parametrize("native_load_fails", [False, True])
def test_native_load_failure_retains_the_initialized_tcl_root(
    monkeypatch: pytest.MonkeyPatch, native_load_fails: bool
) -> None:
    interpreter = tk.Tcl()

    class NativeRoot:
        """Model tkdnd's native require step after a real Tcl root is created."""

        def __init__(self) -> None:
            self.tk = interpreter.tk
            self.tk.call("set", "application_state", "initialized")
            if native_load_fails:
                raise RuntimeError("Unable to load tkdnd library")

    backend = SimpleNamespace(TkinterDnD=SimpleNamespace(Tk=NativeRoot))
    monkeypatch.setattr(
        dragdrop_module.importlib, "import_module", lambda _name: backend
    )

    root, available = dragdrop_module.create_drop_root()

    assert available is not native_load_fails
    assert root.tk.call("set", "application_state") == "initialized"
    root.tk.call("set", "application_state", "ready")
    assert root.tk.call("set", "application_state") == "ready"
