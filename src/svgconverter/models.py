"""Public data models shared by SVGConverter's conversion layers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .errors import SVGConverterError

ConversionMode = Literal["embed", "vectorize"]
VectorizeColorMode = Literal["color", "binary"]
VectorizeHierarchy = Literal["stacked", "cutout"]
VectorizeCurveMode = Literal["pixel", "polygon", "spline"]


@dataclass(frozen=True)
class EmbedOptions:
    """Opt-in preprocessing options for raster bytes embedded in an SVG.

    Images are left byte-for-byte unchanged when all options use their defaults.
    ``max_width`` and ``max_height`` only downscale and always preserve the
    aspect ratio. JPEG and PNG options apply only to their respective formats,
    which makes a single batch configuration safe for mixed input files.
    """

    max_width: int | None = None
    max_height: int | None = None
    jpeg_quality: int | None = None
    png_compress_level: int | None = None
    optimize_png: bool = False

    def __post_init__(self) -> None:
        for name, value in (
            ("max_width", self.max_width),
            ("max_height", self.max_height),
        ):
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be a positive integer.")
        if self.jpeg_quality is not None and not 1 <= self.jpeg_quality <= 95:
            raise ValueError("jpeg_quality must be between 1 and 95.")
        if (
            self.png_compress_level is not None
            and not 0 <= self.png_compress_level <= 9
        ):
            raise ValueError("png_compress_level must be between 0 and 9.")

    @property
    def is_enabled(self) -> bool:
        """Return whether any preprocessing or re-encoding was requested."""

        return any(
            (
                self.max_width is not None,
                self.max_height is not None,
                self.jpeg_quality is not None,
                self.png_compress_level is not None,
                self.optimize_png,
            )
        )


@dataclass(frozen=True)
class VectorizeOptions:
    """VTracer options used by the ``vectorize`` conversion mode.

    The defaults work well for colour illustrations. Use ``color_mode="binary"``
    for high-contrast line art. ``filter_speckle`` removes very small regions,
    while ``color_precision`` and ``layer_difference`` trade colour detail for
    a simpler output.
    """

    color_mode: VectorizeColorMode = "color"
    hierarchical: VectorizeHierarchy = "stacked"
    curve_mode: VectorizeCurveMode = "spline"
    filter_speckle: int | None = None
    color_precision: int | None = None
    layer_difference: int | None = None
    path_precision: int | None = None

    def as_vtracer_kwargs(self) -> dict[str, str | int]:
        """Return keyword arguments understood by VTracer's stable API."""

        options: dict[str, str | int] = {
            "colormode": self.color_mode,
            "hierarchical": self.hierarchical,
            "mode": self.curve_mode,
        }
        optional_values = {
            "filter_speckle": self.filter_speckle,
            "color_precision": self.color_precision,
            "layer_difference": self.layer_difference,
            "path_precision": self.path_precision,
        }
        options.update(
            {
                name: value
                for name, value in optional_values.items()
                if value is not None
            }
        )
        return options


@dataclass(frozen=True)
class ConversionFailure:
    """One failed item from a batch conversion."""

    input_path: Path
    error: SVGConverterError


@dataclass(frozen=True)
class ConversionSkip:
    """One intentionally unmodified item from a batch conversion."""

    input_path: Path
    output_path: Path
    reason: str


@dataclass(frozen=True)
class ConversionMetrics:
    """Input, embedded-raster, and SVG sizes for one converted item."""

    input_path: Path
    output_path: Path
    input_bytes: int
    svg_bytes: int
    embedded_raster_bytes: int | None


@dataclass(frozen=True)
class ConversionProgress:
    """One completed item in a batch conversion.

    ``completed`` and ``total`` describe only the planned source/output pairs.
    Invalid explicit paths are still reported in the final :class:`BatchResult`.
    """

    input_path: Path
    completed: int
    total: int
    converted: int
    skipped: int
    failed: int


ProgressCallback = Callable[[ConversionProgress], None]
CancelCallback = Callable[[], bool]


@dataclass(frozen=True)
class BatchResult:
    """Successful, skipped, and failed items from a batch conversion."""

    converted: tuple[Path, ...]
    failed: tuple[ConversionFailure, ...]
    skipped: tuple[ConversionSkip, ...] = ()
    metrics: tuple[ConversionMetrics, ...] = ()
    cancelled: bool = False

    @property
    def success_count(self) -> int:
        """Return the number of converted images."""

        return len(self.converted)

    @property
    def failure_count(self) -> int:
        """Return the number of files that could not be converted."""

        return len(self.failed)

    @property
    def skipped_count(self) -> int:
        """Return the number of existing outputs left unchanged."""

        return len(self.skipped)

    @property
    def total_input_bytes(self) -> int:
        """Return the total size of successfully converted source files."""

        return sum(metric.input_bytes for metric in self.metrics)

    @property
    def total_svg_bytes(self) -> int:
        """Return the total size of successfully written SVG files."""

        return sum(metric.svg_bytes for metric in self.metrics)

    @property
    def total_embedded_raster_bytes(self) -> int | None:
        """Return embedded-raster bytes, or ``None`` when nothing was embedded."""

        embedded_sizes = [
            metric.embedded_raster_bytes
            for metric in self.metrics
            if metric.embedded_raster_bytes is not None
        ]
        return sum(embedded_sizes) if embedded_sizes else None
