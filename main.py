"""Compatibility launcher for the desktop app and standalone conversion checks."""

from __future__ import annotations

import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Start the GUI, run ``--cli``, or export a PNG with ``--preview``."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "--cli":
        from svgconverter.cli import main as run_cli

        return run_cli(arguments[1:])
    if arguments and arguments[0] == "--preview":
        from svgconverter.preview_cli import main as run_preview

        return run_preview(arguments[1:])

    from svgconverter.gui import run_gui

    run_gui()
    return 0


if __name__ == "__main__":
    from multiprocessing import freeze_support

    freeze_support()
    raise SystemExit(main())
