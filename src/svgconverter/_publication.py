"""Publish a staged file without replacing an existing destination."""

from __future__ import annotations

import ctypes
import errno
import os
import sys
from pathlib import Path


def _rename_without_overwrite(source: Path, destination: Path) -> None:
    if sys.platform == "win32":
        # Windows rename raises FileExistsError instead of replacing a file.
        os.rename(source, destination)
        return

    library = ctypes.CDLL(None, use_errno=True)
    try:
        if sys.platform == "linux":
            rename = library.renameat2
            rename.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            # Use the current working directory and the no-replace rename flag.
            arguments = (-100, os.fsencode(source), -100, os.fsencode(destination), 1)
        elif sys.platform == "darwin":
            rename = library.renamex_np
            rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
            # Request an exclusive rename on macOS.
            arguments = (os.fsencode(source), os.fsencode(destination), 4)
        else:
            raise OSError(errno.ENOTSUP, "exclusive rename is unavailable")
    except AttributeError as error:
        raise OSError(errno.ENOTSUP, "exclusive rename is unavailable") from error
    rename.restype = ctypes.c_int
    if rename(*arguments) != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), str(destination))


def publish_without_overwrite(source: Path, destination: Path) -> None:
    """Use a hard link or an exclusive rename, never a replacing rename."""
    try:
        os.link(source, destination)
    except OSError as error:
        if error.errno not in {
            errno.EPERM,
            errno.EINVAL,
            errno.ENOSYS,
            errno.ENOTSUP,
        }:
            raise
        _rename_without_overwrite(source, destination)
