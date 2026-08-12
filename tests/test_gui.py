from __future__ import annotations

from pathlib import Path

from svgconverter import BatchResult, ConversionError, ConversionFailure
from svgconverter.gui import format_failure_details


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
