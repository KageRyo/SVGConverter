"""Command-line interface for SVGConverter."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .converter import (
    BatchResult,
    SVGConverterError,
    VectorizeOptions,
    convert_directory,
    convert_file,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the ``svgconverter`` command parser."""

    parser = argparse.ArgumentParser(
        prog="svgconverter",
        description=(
            "Convert PNG, JPEG, WebP, BMP, or TIFF images to SVG by embedding "
            "or vectorizing them."
        ),
    )
    parser.add_argument(
        "input",
        type=Path,
        help="PNG/JPEG/WebP/BMP/TIFF file or a directory of images",
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
        choices=("embed", "vectorize"),
        default="embed",
        help="Conversion mode: embed preserves raster pixels; vectorize traces paths",
    )
    vectorize_group = parser.add_argument_group("vectorize options")
    vectorize_group.add_argument(
        "--vectorize-color-mode",
        choices=("color", "binary"),
        default="color",
        help="Trace colour regions or high-contrast binary artwork",
    )
    vectorize_group.add_argument(
        "--vectorize-hierarchical",
        choices=("stacked", "cutout"),
        default="stacked",
        help="Use stacked paths or cutout regions while vectorizing",
    )
    vectorize_group.add_argument(
        "--vectorize-curve-mode",
        choices=("pixel", "polygon", "spline"),
        default="spline",
        help="Curve-fitting strategy while vectorizing",
    )
    vectorize_group.add_argument(
        "--filter-speckle",
        type=int,
        help="Discard vectorized regions smaller than this pixel count",
    )
    vectorize_group.add_argument(
        "--color-precision",
        type=int,
        help="Significant RGB bits to retain in vectorize mode",
    )
    vectorize_group.add_argument(
        "--layer-difference",
        type=int,
        help="Minimum colour difference between vectorized layers",
    )
    vectorize_group.add_argument(
        "--path-precision",
        type=int,
        help="Decimal places to retain in generated path coordinates",
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


def _vectorize_options_from_arguments(
    arguments: argparse.Namespace,
) -> VectorizeOptions:
    return VectorizeOptions(
        color_mode=arguments.vectorize_color_mode,
        hierarchical=arguments.vectorize_hierarchical,
        curve_mode=arguments.vectorize_curve_mode,
        filter_speckle=arguments.filter_speckle,
        color_precision=arguments.color_precision,
        layer_difference=arguments.layer_difference,
        path_precision=arguments.path_precision,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    parser = build_parser()
    arguments = parser.parse_args(argv)
    vectorize_options = _vectorize_options_from_arguments(arguments)
    try:
        if arguments.input.is_file():
            if arguments.output_dir is not None:
                parser.error("--output-dir can only be used with a directory input")
            output_path = convert_file(
                arguments.input,
                arguments.output,
                overwrite=arguments.overwrite,
                mode=arguments.mode,
                vectorize_options=vectorize_options,
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
            vectorize_options=vectorize_options,
        )
        _print_batch_result(result)
        return 1 if result.failed else 0
    except SVGConverterError as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
