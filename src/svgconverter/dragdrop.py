"""Optional native file dropping and path normalization for the desktop UI."""

import importlib
import logging
import os
import tkinter as tk
from collections.abc import Iterable
from pathlib import Path

from .embed import SUPPORTED_EXTENSIONS

_LOGGER = logging.getLogger(__name__)


def create_drop_root() -> tuple[tk.Tk, bool]:
    """Keep ordinary Tk usable when the optional native extension is unavailable."""

    try:
        backend = importlib.import_module("tkinterdnd2")
    except ImportError:
        return tk.Tk(), False

    class OptionalDropRoot(backend.TkinterDnD.Tk):
        def __init__(self) -> None:
            self.drop_available = True
            try:
                super().__init__()
            except RuntimeError:
                # TkinterDnD creates Tk before requiring its native extension.
                # Retain that initialized root when tkdnd cannot be loaded.
                self.drop_available = False
                _LOGGER.debug(
                    "Native drag-and-drop support could not load.", exc_info=True
                )

    root = OptionalDropRoot()
    return root, root.drop_available


def normalize_drop_paths(
    paths: Iterable[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Resolve/deduplicate supported files and folders without scanning contents."""

    accepted: list[str] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for item in paths:
        try:
            path = Path(item).expanduser().resolve()
            key = os.path.normcase(str(path))
            if key in seen:
                continue
            seen.add(key)
            if path.is_dir() or (
                path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
            ):
                accepted.append(str(path))
            else:
                rejected.append(item)
        except (OSError, ValueError, RuntimeError):
            rejected.append(item)
    return tuple(accepted), tuple(rejected)
