"""Exercise native Tk initialization and one event-loop turn on a display."""

from __future__ import annotations

import tkinter

from svgconverter.gui import SVGConverterApp

app = SVGConverterApp()
failures: list[str] = []


def verify_window() -> None:
    try:
        if not app.root.winfo_viewable():
            failures.append("The application window did not become viewable.")
        print(f"Native GUI initialized with Tcl/Tk {tkinter.TkVersion}.")
    finally:
        app.root.destroy()


app.root.after(250, verify_window)
app.run()
if failures:
    raise RuntimeError(" ".join(failures))
