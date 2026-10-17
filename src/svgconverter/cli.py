"""Command-line interface for SVGConverter."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .converter import (
    BatchResult,
    ConversionFailure,
    ConversionMetrics,
    EmbedOptions,
    SVGConverterError,
    VectorizeOptions,
    convert_directory,
    convert_file_with_metrics,
    convert_paths,
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
        "inputs",
        type=Path,
        nargs="+",
        metavar="INPUT",
        help="PNG/JPEG/WebP/BMP/TIFF files and/or directories of images",
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
        help="Output directory for one or more files or directories",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace existing output SVG files"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Write one versioned JSON report to stdout instead of human-readable text",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Include supported images in nested directories",
    )
    parser.add_argument(
        "--allowed-root",
        type=Path,
        help=(
            "Restrict input and output paths to this directory; use this when "
            "paths originate from an untrusted caller"
        ),
    )
    embed_group = parser.add_argument_group("embed optimization options")
    embed_group.add_argument(
        "--max-width",
        type=int,
        help="Downscale embedded rasters to this maximum width; preserves aspect ratio",
    )
    embed_group.add_argument(
        "--max-height",
        type=int,
        help="Downscale rasters to this maximum height; preserves aspect ratio",
    )
    embed_group.add_argument(
        "--jpeg-quality",
        type=int,
        help="JPEG re-encoding quality from 1 to 95; applies only to JPEG inputs",
    )
    embed_group.add_argument(
        "--png-compress-level",
        type=int,
        help="PNG compression level from 0 to 9; applies only to PNG inputs",
    )
    embed_group.add_argument(
        "--optimize-png",
        action="store_true",
        help="Enable Pillow's PNG optimizer; applies only to PNG inputs",
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


def _print_json_result(
    result: BatchResult,
    arguments: argparse.Namespace,
    *,
    error: Exception | None = None,
) -> None:
    """Write the version 1 automation report without progress or summary text."""

    report = {
        "schema_version": 1,
        "inputs": [str(path) for path in arguments.inputs],
        "output": str(arguments.output) if arguments.output is not None else None,
        "output_dir": (
            str(arguments.output_dir) if arguments.output_dir is not None else None
        ),
        "mode": arguments.mode,
        "totals": {
            "converted": result.success_count,
            "skipped": result.skipped_count,
            "failed": result.failure_count,
        },
        "converted": [
            {
                "input_path": str(metric.input_path),
                "output_path": str(metric.output_path),
                "input_bytes": metric.input_bytes,
                "svg_bytes": metric.svg_bytes,
                "embedded_raster_bytes": metric.embedded_raster_bytes,
            }
            for metric in result.metrics
        ],
        "skipped": [
            {
                "input_path": str(skip.input_path),
                "output_path": str(skip.output_path),
                "reason": skip.reason,
            }
            for skip in result.skipped
        ],
        "failed": [
            {
                "input_path": str(failure.input_path),
                "error": str(failure.error),
                "error_type": type(failure.error).__name__,
            }
            for failure in result.failed
        ],
        "cancelled": result.cancelled,
        "sizes": {
            "input_bytes": result.total_input_bytes,
            "svg_bytes": result.total_svg_bytes,
            "embedded_raster_bytes": result.total_embedded_raster_bytes,
        },
        "error": (
            {"error": str(error), "error_type": type(error).__name__}
            if error is not None
            else None
        ),
    }
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))


def _print_batch_result(result: BatchResult) -> None:
    for output_path in result.converted:
        print(f"Converted: {output_path}")
    for skip in result.skipped:
        print(f"Skipped: {skip.input_path} -> {skip.output_path} ({skip.reason})")
    for failure in result.failed:
        print(f"Failed: {failure.input_path}: {failure.error}")
    print(
        "Summary: "
        f"{result.success_count} converted, {result.skipped_count} skipped, "
        f"{result.failure_count} failed"
    )
    if result.metrics:
        embedded_raster_bytes = result.total_embedded_raster_bytes
        if embedded_raster_bytes is None:
            print(
                "Size summary: "
                f"{_format_bytes(result.total_input_bytes)} input, "
                f"{_format_bytes(result.total_svg_bytes)} SVG"
            )
        else:
            print(
                "Size summary: "
                f"{_format_bytes(result.total_input_bytes)} input, "
                f"{_format_bytes(embedded_raster_bytes)} embedded raster, "
                f"{_format_bytes(result.total_svg_bytes)} SVG"
            )


def _format_bytes(byte_count: int) -> str:
    """Format byte counts compactly for command-line conversion summaries."""

    value = float(byte_count)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def _print_conversion_metrics(metric: ConversionMetrics) -> None:
    """Print the sizes for one converted file."""

    if metric.embedded_raster_bytes is None:
        print(
            "Sizes: "
            f"{_format_bytes(metric.input_bytes)} input, "
            f"{_format_bytes(metric.svg_bytes)} SVG"
        )
        return
    print(
        "Sizes: "
        f"{_format_bytes(metric.input_bytes)} input, "
        f"{_format_bytes(metric.embedded_raster_bytes)} embedded raster, "
        f"{_format_bytes(metric.svg_bytes)} SVG"
    )


def _print_single_result(
    metric: ConversionMetrics, arguments: argparse.Namespace
) -> None:
    if arguments.json:
        _print_json_result(
            BatchResult((metric.output_path,), (), metrics=(metric,)), arguments
        )
    else:
        print(f"Converted: {metric.output_path}")
        _print_conversion_metrics(metric)


def _print_json_error(
    error: SVGConverterError | ValueError,
    arguments: argparse.Namespace,
    *,
    single_file: bool,
) -> None:
    if single_file and isinstance(error, SVGConverterError):
        _print_json_result(
            BatchResult((), (ConversionFailure(arguments.inputs[0], error),)), arguments
        )
    else:
        _print_json_result(BatchResult((), ()), arguments, error=error)


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


def _embed_options_from_arguments(arguments: argparse.Namespace) -> EmbedOptions:
    """Create embed preprocessing options from parsed command-line arguments."""

    return EmbedOptions(
        max_width=arguments.max_width,
        max_height=arguments.max_height,
        jpeg_quality=arguments.jpeg_quality,
        png_compress_level=arguments.png_compress_level,
        optimize_png=arguments.optimize_png,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    parser = build_parser()
    arguments = parser.parse_args(argv)
    vectorize_options = _vectorize_options_from_arguments(arguments)
    try:
        embed_options = _embed_options_from_arguments(arguments)
    except ValueError as error:
        parser.error(str(error))
    single_file = (
        len(arguments.inputs) == 1
        and arguments.inputs[0].is_file()
        and arguments.output_dir is None
    )
    try:
        if single_file:
            metric = convert_file_with_metrics(
                arguments.inputs[0],
                arguments.output,
                overwrite=arguments.overwrite,
                mode=arguments.mode,
                vectorize_options=vectorize_options,
                embed_options=embed_options,
                allowed_root=arguments.allowed_root,
            )
            _print_single_result(metric, arguments)
            return 0

        if arguments.output is not None:
            parser.error("--output can only be used with a single input file")

        if len(arguments.inputs) == 1 and not arguments.inputs[0].is_file():
            result = convert_directory(
                arguments.inputs[0],
                arguments.output_dir,
                overwrite=arguments.overwrite,
                recursive=arguments.recursive,
                mode=arguments.mode,
                vectorize_options=vectorize_options,
                embed_options=embed_options,
                allowed_root=arguments.allowed_root,
            )
        else:
            result = convert_paths(
                arguments.inputs,
                arguments.output_dir,
                overwrite=arguments.overwrite,
                recursive=arguments.recursive,
                mode=arguments.mode,
                vectorize_options=vectorize_options,
                embed_options=embed_options,
                allowed_root=arguments.allowed_root,
            )
        if arguments.json:
            _print_json_result(result, arguments)
        else:
            _print_batch_result(result)
        return 1 if result.failed or result.cancelled else 0
    except (SVGConverterError, ValueError) as error:
        if arguments.json:
            _print_json_error(error, arguments, single_file=single_file)
            return 1
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
