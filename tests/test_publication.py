from __future__ import annotations

import errno
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from svgconverter import _publication


@pytest.mark.parametrize(
    ("platform", "symbol", "arguments"),
    [
        ("linux", "renameat2", (-100, b"source", -100, b"destination", 1)),
        ("darwin", "renamex_np", (b"source", b"destination", 4)),
    ],
)
@pytest.mark.parametrize("error_number", [0, errno.EEXIST, errno.ENOTSUP])
def test_exclusive_rename_native_arguments_and_errors(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    symbol: str,
    arguments: tuple[object, ...],
    error_number: int,
) -> None:
    rename = Mock(return_value=-1 if error_number else 0)
    library = Mock(return_value=SimpleNamespace(**{symbol: rename}))
    monkeypatch.setattr(_publication.sys, "platform", platform)
    monkeypatch.setattr(_publication.ctypes, "CDLL", library)
    monkeypatch.setattr(_publication.ctypes, "get_errno", lambda: error_number)

    if error_number:
        with pytest.raises(OSError) as error:
            _publication._rename_without_overwrite(Path("source"), Path("destination"))
        assert error.value.errno == error_number
        if error_number == errno.EEXIST:
            assert isinstance(error.value, FileExistsError)
    else:
        _publication._rename_without_overwrite(Path("source"), Path("destination"))

    library.assert_called_once_with(None, use_errno=True)
    rename.assert_called_once_with(*arguments)


def test_missing_exclusive_rename_does_not_replace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_publication.sys, "platform", "linux")
    monkeypatch.setattr(_publication.ctypes, "CDLL", lambda *a, **kw: object())
    with pytest.raises(OSError) as error:
        _publication._rename_without_overwrite(Path("source"), Path("destination"))
    assert error.value.errno == errno.ENOTSUP


def test_windows_uses_non_replacing_rename(monkeypatch: pytest.MonkeyPatch) -> None:
    rename = Mock(side_effect=FileExistsError(errno.EEXIST, "existing output"))
    monkeypatch.setattr(_publication.sys, "platform", "win32")
    monkeypatch.setattr(_publication.os, "rename", rename)
    with pytest.raises(FileExistsError):
        _publication._rename_without_overwrite(Path("source"), Path("destination"))
    rename.assert_called_once_with(Path("source"), Path("destination"))
