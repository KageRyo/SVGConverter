"""Command-line interface for SVGConverter."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .converter import BatchResult, SVGConverterError, convert_directory, convert_file


def build_parser() -> argparse.ArgumentParser:
    """Build the ``svgconverter`` command parser."""

    parser = argparse.ArgumentParser(
        prog="svgconverter",
        description=(
            "Embed a PNG or JPEG raster image in an SVG container. "
            "This does not vectorize the image."
        ),
    )
    parser.add_argument(
        "input", type=Path, help="PNG/JPG/JPEG file or a directory of images"
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output SVG path for a single input file",
    )
    output_group.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for a directory input",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace existing output SVG files"
    )
    parser.add_argument(
        "--mode",
        choices=("embed",),
        default="embed",
        help="Conversion mode (only embed is currently available)",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def _print_batch_result(result: BatchResult) -> None:
    for output_path in result.converted:
        print(f"Converted: {output_path}")
    for failure in result.failed:
        print(f"Failed: {failure.input_path}: {failure.error}")
    print(f"Summary: {result.success_count} converted, {result.failure_count} failed")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.input.is_file():
            if arguments.output_dir is not None:
                parser.error("--output-dir can only be used with a directory input")
            output_path = convert_file(
                arguments.input,
                arguments.output,
                overwrite=arguments.overwrite,
                mode=arguments.mode,
            )
            print(f"Converted: {output_path}")
            return 0

        if arguments.output is not None:
            parser.error("--output can only be used with a single input file")
        result = convert_directory(
            arguments.input,
            arguments.output_dir,
            overwrite=arguments.overwrite,
            mode=arguments.mode,
        )
        _print_batch_result(result)
        return 1 if result.failed else 0
    except SVGConverterError as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
