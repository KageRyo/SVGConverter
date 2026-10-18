"""Opt-in integration checks for native Tk/tkdnd registration and event delivery."""

from __future__ import annotations

import logging
import os
import platform
import sys
import tkinter
from collections.abc import Iterator
from importlib.metadata import version
from pathlib import Path

import pytest
from PIL import Image

from svgconverter.gui import SVGConverterApp

pytestmark = pytest.mark.skipif(
    os.environ.get("SVGCONVERTER_NATIVE_GUI") != "1",
    reason="Set SVGCONVERTER_NATIVE_GUI=1 with a display and compatible tkinterdnd2",
)


def library_files(app: SVGConverterApp) -> tuple[Path, ...]:
    tcl_library = Path(str(app.root.tk.call("info", "library")))
    tk_library = Path(str(app.root.tk.call("set", "tk_library")))
    return (
        tcl_library / "init.tcl",
        tk_library / "tk.tcl",
        tk_library / "menu.tcl",
    )


def check_library_files(paths: tuple[Path, ...], stage: str) -> None:
    for path in paths:
        print(f"{stage}: {path} exists={path.is_file()}")
        assert path.is_file(), f"Native Tcl/Tk library file is missing: {path}"


@pytest.fixture(scope="module")
def native_application() -> Iterator[SVGConverterApp]:
    """Keep one native Tk interpreter for the application's complete lifetime.

    Tk/tkdnd state is interpreter-owned. These scenarios exercise one application's
    selection states rather than repeated teardown/reinitialization of native Tk.
    """

    print(
        f"Native runtime: {platform.system()} {platform.machine()}, "
        f"Python {platform.python_version()}, Tcl/Tk "
        f"{tkinter.TclVersion}/{tkinter.TkVersion}, "
        f"tkinterdnd2 {version('tkinterdnd2')}"
    )
    for script in (Path(sys.base_prefix) / "tcl").glob("tcl*/init.tcl"):
        print(f"Interpreter Tcl startup script: {script} (exists={script.is_file()})")
    logger = logging.getLogger("svgconverter.dragdrop")
    previous_level = logger.level
    try:
        logger.setLevel(logging.DEBUG)
        app = SVGConverterApp()
    finally:
        logger.setLevel(previous_level)
    paths: tuple[Path, ...] = ()
    try:
        paths = library_files(app)
        check_library_files(paths, "After native startup")
        if not app._drop_available:
            # The normal GUI retains working pickers when loading fails. In this
            # explicit native check, surface Tcl's original load error as well.
            app.root.tk.call("package", "require", "tkdnd")
        assert app._drop_available, "Native tkinterdnd2 must load for this smoke check"
        app.root.update()
        yield app
    finally:
        app.root.destroy()
        check_library_files(paths, "After application teardown")


@pytest.fixture
def native_app(native_application: SVGConverterApp) -> Iterator[SVGConverterApp]:
    app = native_application
    app._cancel_event.clear()
    app._set_running(False)
    app.reset_for_new_conversion()
    app.root.update()
    paths = library_files(app)
    check_library_files(paths, "Before drop scenario")
    try:
        yield app
    finally:
        app._set_running(False)
        app.reset_for_new_conversion()
        app.root.update()
        check_library_files(paths, "After drop scenario")


def deliver_file_drop(app: SVGConverterApp, paths: tuple[Path, ...]) -> str:
    """Deliver a Tcl file-drop through tkdnd's registered target and binding.

    This exercises native loading, target registration, Tcl list quoting, and
    the actual Python callback without requiring an OS file-manager gesture.
    """

    target = str(app.drop_target)
    tk = app.root.tk
    types = tk.call("tkdnd::platform_specific_types", ("DND_Files",))
    tk.call("tkdnd::generic::SetDroppedData", tk.call("list", *map(str, paths)))
    tk.call(
        "tkdnd::generic::HandleEnter",
        target,
        "test-source",
        types,
        types,
        ("copy",),
        (),
    )
    tk.call("tkdnd::generic::HandlePosition", target, "test-source", (), 0, 0)
    return str(
        tk.call("tkdnd::generic::HandleDrop", target, "test-source", (), 0, 0, 0)
    )


def test_native_drop_appends_mixed_unicode_paths_without_starting_conversion(
    tmp_path: Path, native_app: SVGConverterApp
) -> None:
    previous = tmp_path / "previous.png"
    source = tmp_path / "image spaces 漢字.png"
    for path in (previous, source):
        Image.new("RGB", (2, 2)).save(path)
    folder = tmp_path / "folder spaces 日本語"
    folder.mkdir()
    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("notes", encoding="utf-8")
    native_app._set_selected_inputs((str(previous),), "files")

    action = deliver_file_drop(native_app, (source, folder, source, unsupported))

    assert action == "copy"
    assert native_app._selected_input_paths == tuple(
        str(path.resolve()) for path in (previous, source, folder)
    )
    assert native_app._selected_input_kind == "mixed"
    assert unsupported.name in native_app.status_var.get()
    assert native_app._worker is None
    assert not native_app._running
    assert not list(tmp_path.rglob("*.svg"))


def test_native_drop_refuses_selection_changes_during_conversion(
    tmp_path: Path, native_app: SVGConverterApp
) -> None:
    source = tmp_path / "image spaces 漢字.png"
    Image.new("RGB", (2, 2)).save(source)
    previous = (str(tmp_path / "previous.png"),)
    native_app._set_selected_inputs(previous, "files")
    native_app._set_running(True)

    action = deliver_file_drop(native_app, (source,))

    assert action == "refuse_drop"
    assert native_app._selected_input_paths == previous
    assert native_app._worker is None
    assert not list(tmp_path.rglob("*.svg"))
