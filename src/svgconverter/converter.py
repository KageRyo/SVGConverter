"""Core image conversion functionality.

The ``embed`` mode deliberately stores source raster bytes in an SVG ``<image>``
element. It does not turn pixels into vector paths; ``vectorize`` provides that
separate optional mode.
"""

from __future__ import annotations

import base64
import importlib
from collections.abc import Iterable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal

from PIL import Image, UnidentifiedImageError

ConversionMode = Literal["embed", "vectorize"]
VectorizeColorMode = Literal["color", "binary"]
VectorizeHierarchy = Literal["stacked", "cutout"]
VectorizeCurveMode = Literal["pixel", "polygon", "spline"]

_SUPPORTED_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
)
_MIME_TYPES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
}


class SVGConverterError(Exception):
    """Base exception for expected SVGConverter failures."""


class InputPathError(SVGConverterError):
    """Raised when an input path is missing or is the wrong kind of path."""


class UnsupportedImageError(SVGConverterError):
    """Raised when an input is not a supported raster image."""


class OutputExistsError(SVGConverterError):
    """Raised when conversion would overwrite an existing SVG."""


class OutputCollisionError(SVGConverterError):
    """Raised when batch inputs would create the same output SVG path."""


class ConversionError(SVGConverterError):
    """Raised when an image cannot be read or an SVG cannot be written."""


class VectorizationDependencyError(SVGConverterError):
    """Raised when vectorize mode is used without its optional backend."""


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
class BatchResult:
    """Successful, skipped, and failed items from a batch conversion."""

    converted: tuple[Path, ...]
    failed: tuple[ConversionFailure, ...]
    skipped: tuple[ConversionSkip, ...] = ()
    metrics: tuple[ConversionMetrics, ...] = ()

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


def _validate_mode(mode: ConversionMode) -> None:
    if mode not in ("embed", "vectorize"):
        raise ValueError("mode must be either 'embed' or 'vectorize'.")


def _validate_embed_options(
    mode: ConversionMode, embed_options: EmbedOptions | None
) -> None:
    if mode == "vectorize" and embed_options is not None and embed_options.is_enabled:
        raise ValueError("embed_options can only be used with mode='embed'.")


def _validate_input(input_path: Path) -> None:
    if not input_path.exists():
        raise InputPathError(f"Input file does not exist: {input_path}")
    if not input_path.is_file():
        raise InputPathError(f"Input path is not a file: {input_path}")
    if input_path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(_SUPPORTED_EXTENSIONS))
        raise UnsupportedImageError(
            f"Unsupported image extension {input_path.suffix!r}; "
            f"supported extensions: {supported}"
        )


def _read_image_metadata(input_path: Path) -> tuple[int, int, str]:
    try:
        with Image.open(input_path) as image:
            image.verify()
        with Image.open(input_path) as image:
            mime_type = _MIME_TYPES.get(image.format or "")
            if mime_type is None:
                raise UnsupportedImageError(
                    f"Unsupported image format in {input_path}: "
                    f"{image.format or 'unknown'}"
                )
            return image.width, image.height, mime_type
    except UnsupportedImageError:
        raise
    except (OSError, UnidentifiedImageError) as error:
        raise ConversionError(f"Cannot read image {input_path}: {error}") from error


def _svg_document(*, data_uri: str, width: int, height: int) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        f'  <image href="{data_uri}" width="{width}" height="{height}"/>\n'
        "</svg>\n"
    )


def _target_dimensions(
    width: int, height: int, embed_options: EmbedOptions
) -> tuple[int, int]:
    """Return downscaled dimensions that honour every configured maximum."""

    scale_limits = [1.0]
    if embed_options.max_width is not None:
        scale_limits.append(embed_options.max_width / width)
    if embed_options.max_height is not None:
        scale_limits.append(embed_options.max_height / height)
    scale = min(scale_limits)
    return max(1, round(width * scale)), max(1, round(height * scale))


def _image_save_kwargs(
    image: Image.Image, image_format: str, embed_options: EmbedOptions
) -> dict[str, object]:
    """Return format-specific Pillow options for requested raster optimization."""

    save_kwargs: dict[str, object] = {}
    if icc_profile := image.info.get("icc_profile"):
        save_kwargs["icc_profile"] = icc_profile
    if exif := image.info.get("exif"):
        save_kwargs["exif"] = exif

    if image_format == "JPEG":
        if embed_options.jpeg_quality is None:
            save_kwargs["quality"] = 95
        else:
            save_kwargs["quality"] = embed_options.jpeg_quality
    elif image_format == "PNG":
        if embed_options.png_compress_level is not None:
            save_kwargs["compress_level"] = embed_options.png_compress_level
        if embed_options.optimize_png:
            save_kwargs["optimize"] = True
    return save_kwargs


def _embedded_raster(
    source: Path, embed_options: EmbedOptions | None
) -> tuple[bytes, int, int, str]:
    """Return source bytes or explicitly requested optimized raster bytes."""

    width, height, mime_type = _read_image_metadata(source)
    source_data = source.read_bytes()
    if embed_options is None or not embed_options.is_enabled:
        return source_data, width, height, mime_type

    try:
        with Image.open(source) as image:
            image_format = image.format
            if image_format is None:
                raise UnsupportedImageError(
                    f"Unsupported image format in {source}: unknown"
                )
            target_width, target_height = _target_dimensions(
                image.width, image.height, embed_options
            )
            should_resize = (target_width, target_height) != image.size
            should_reencode = (
                should_resize
                or (image_format == "JPEG" and embed_options.jpeg_quality is not None)
                or (
                    image_format == "PNG"
                    and (
                        embed_options.png_compress_level is not None
                        or embed_options.optimize_png
                    )
                )
            )
            if not should_reencode:
                return source_data, width, height, mime_type

            image.load()
            if should_resize:
                image = image.resize(
                    (target_width, target_height), Image.Resampling.LANCZOS
                )
            data = BytesIO()
            image.save(
                data,
                format=image_format,
                **_image_save_kwargs(image, image_format, embed_options),
            )
            return data.getvalue(), image.width, image.height, mime_type
    except UnsupportedImageError:
        raise
    except (OSError, ValueError) as error:
        raise ConversionError(f"Cannot optimize image {source}: {error}") from error


def _embed_image(
    source: Path, destination: Path, embed_options: EmbedOptions | None
) -> int:
    image_data, width, height, mime_type = _embedded_raster(source, embed_options)
    data_uri = f"data:{mime_type};base64,{base64.b64encode(image_data).decode('ascii')}"
    destination.write_text(
        _svg_document(data_uri=data_uri, width=width, height=height), encoding="utf-8"
    )
    return len(image_data)


def _load_vtracer() -> object:
    try:
        return importlib.import_module("vtracer")
    except ModuleNotFoundError as error:
        raise VectorizationDependencyError(
            "Vectorize mode requires the optional VTracer backend. "
            "Install it with: pip install 'svgconverter[vectorize]'"
        ) from error


def _vectorize_image(
    source: Path, destination: Path, vectorize_options: VectorizeOptions
) -> None:
    vtracer = _load_vtracer()
    try:
        vtracer.convert_image_to_svg_py(  # type: ignore[attr-defined]
            str(source), str(destination), **vectorize_options.as_vtracer_kwargs()
        )
    except Exception as error:
        raise ConversionError(f"Cannot vectorize image {source}: {error}") from error

    if not destination.is_file():
        raise ConversionError(f"Vectorization did not create an SVG: {destination}")


def _validate_output_directory(destination_directory: Path) -> None:
    if destination_directory.exists() and not destination_directory.is_dir():
        raise InputPathError(
            f"Output directory path is not a directory: {destination_directory}"
        )


def _directory_candidates(
    source_directory: Path,
    destination_directory: Path,
    *,
    recursive: bool,
) -> list[tuple[Path, Path]]:
    entries = source_directory.rglob("*") if recursive else source_directory.iterdir()
    sources = sorted(
        (
            path
            for path in entries
            if path.is_file() and path.suffix.lower() in _SUPPORTED_EXTENSIONS
        ),
        key=lambda path: str(path.relative_to(source_directory)).casefold(),
    )
    return [
        (
            source,
            destination_directory
            / source.relative_to(source_directory).with_suffix(".svg"),
        )
        for source in sources
    ]


def _convert_candidates(
    candidates: Iterable[tuple[Path, Path]],
    *,
    overwrite: bool,
    mode: ConversionMode,
    vectorize_options: VectorizeOptions | None,
    embed_options: EmbedOptions | None,
    initial_failures: Iterable[ConversionFailure] = (),
) -> BatchResult:
    """Convert planned source/output pairs with predictable batch semantics."""

    unique_candidates: list[tuple[Path, Path]] = []
    seen_candidates: set[tuple[Path, Path]] = set()
    for candidate in candidates:
        if candidate not in seen_candidates:
            unique_candidates.append(candidate)
            seen_candidates.add(candidate)

    sources_by_destination: dict[Path, list[Path]] = {}
    for source, destination in unique_candidates:
        sources_by_destination.setdefault(destination, []).append(source)
    colliding_destinations = {
        destination
        for destination, sources in sources_by_destination.items()
        if len(sources) > 1
    }

    converted: list[Path] = []
    skipped: list[ConversionSkip] = []
    metrics: list[ConversionMetrics] = []
    failed = list(initial_failures)
    for source, destination in unique_candidates:
        if destination in colliding_destinations:
            colliding_sources = ", ".join(
                str(candidate) for candidate in sources_by_destination[destination]
            )
            failed.append(
                ConversionFailure(
                    input_path=source,
                    error=OutputCollisionError(
                        "Batch inputs would create the same output "
                        f"{destination}: {colliding_sources}"
                    ),
                )
            )
            continue

        if destination.exists() and destination.is_dir():
            failed.append(
                ConversionFailure(
                    input_path=source,
                    error=InputPathError(f"Output path is a directory: {destination}"),
                )
            )
            continue
        if destination.exists() and not overwrite:
            skipped.append(
                ConversionSkip(
                    input_path=source,
                    output_path=destination,
                    reason="output already exists",
                )
            )
            continue

        try:
            metric = convert_file_with_metrics(
                source,
                destination,
                overwrite=overwrite,
                mode=mode,
                vectorize_options=vectorize_options,
                embed_options=embed_options,
            )
            converted.append(metric.output_path)
            metrics.append(metric)
        except SVGConverterError as error:
            failed.append(ConversionFailure(input_path=source, error=error))

    return BatchResult(
        converted=tuple(converted),
        failed=tuple(failed),
        skipped=tuple(skipped),
        metrics=tuple(metrics),
    )


def convert_file_with_metrics(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    overwrite: bool = False,
    mode: ConversionMode = "embed",
    vectorize_options: VectorizeOptions | None = None,
    embed_options: EmbedOptions | None = None,
) -> ConversionMetrics:
    """Convert one image and return the result path plus byte-size metrics.

    ``output_path`` defaults to the input filename with an ``.svg`` suffix.
    Parent directories for an explicit output path are created automatically.
    Existing outputs are preserved unless ``overwrite=True`` is provided.

    ``mode="embed"`` stores the original raster bytes in an SVG ``<image>``
    element unless enabled ``embed_options`` request preprocessing. ``mode="vectorize"``
    traces the image into vector paths and requires the ``vectorize`` optional
    dependency.
    """

    _validate_mode(mode)
    _validate_embed_options(mode, embed_options)
    source = Path(input_path)
    _validate_input(source)
    destination = (
        Path(output_path) if output_path is not None else source.with_suffix(".svg")
    )

    if destination.exists() and not overwrite:
        raise OutputExistsError(
            f"Output already exists: {destination}. Pass overwrite=True to replace it."
        )
    if destination.exists() and destination.is_dir():
        raise InputPathError(f"Output path is a directory: {destination}")

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if mode == "embed":
            embedded_raster_bytes = _embed_image(source, destination, embed_options)
        else:
            _vectorize_image(
                source, destination, vectorize_options or VectorizeOptions()
            )
            embedded_raster_bytes = None
        return ConversionMetrics(
            input_path=source,
            output_path=destination,
            input_bytes=source.stat().st_size,
            svg_bytes=destination.stat().st_size,
            embedded_raster_bytes=embedded_raster_bytes,
        )
    except OSError as error:
        raise ConversionError(f"Cannot write SVG {destination}: {error}") from error


def convert_file(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    overwrite: bool = False,
    mode: ConversionMode = "embed",
    vectorize_options: VectorizeOptions | None = None,
    embed_options: EmbedOptions | None = None,
) -> Path:
    """Convert one supported raster image and return its output SVG path.

    Use :func:`convert_file_with_metrics` when the input, embedded-raster, and
    SVG byte sizes are also needed.
    """

    return convert_file_with_metrics(
        input_path,
        output_path,
        overwrite=overwrite,
        mode=mode,
        vectorize_options=vectorize_options,
        embed_options=embed_options,
    ).output_path


def convert_directory(
    directory: str | Path,
    output_dir: str | Path | None = None,
    *,
    overwrite: bool = False,
    recursive: bool = False,
    mode: ConversionMode = "embed",
    vectorize_options: VectorizeOptions | None = None,
    embed_options: EmbedOptions | None = None,
) -> BatchResult:
    """Convert supported images in one directory, optionally including children.

    Files with non-image extensions are ignored. Each supported image is
    attempted independently, so a corrupt image does not stop the batch. When
    ``recursive=True`` and ``output_dir`` is supplied, the output mirrors the
    source directory structure. Existing SVGs are skipped unless
    ``overwrite=True`` is supplied.
    """

    _validate_mode(mode)
    _validate_embed_options(mode, embed_options)
    source_directory = Path(directory)
    if not source_directory.exists():
        raise InputPathError(f"Input directory does not exist: {source_directory}")
    if not source_directory.is_dir():
        raise InputPathError(f"Input path is not a directory: {source_directory}")

    destination_directory = (
        Path(output_dir) if output_dir is not None else source_directory
    )
    _validate_output_directory(destination_directory)
    return _convert_candidates(
        _directory_candidates(
            source_directory, destination_directory, recursive=recursive
        ),
        overwrite=overwrite,
        mode=mode,
        vectorize_options=vectorize_options,
        embed_options=embed_options,
    )


def convert_paths(
    input_paths: Iterable[str | Path],
    output_dir: str | Path | None = None,
    *,
    overwrite: bool = False,
    recursive: bool = False,
    mode: ConversionMode = "embed",
    vectorize_options: VectorizeOptions | None = None,
    embed_options: EmbedOptions | None = None,
) -> BatchResult:
    """Convert multiple image files and directories in one batch.

    Directory inputs include only their immediate files by default; pass
    ``recursive=True`` to include nested files. A supplied ``output_dir`` is
    used directly for one directory input and is prefixed with each directory
    name when more than one directory is supplied. This avoids flattening
    separate directory trees into the same output namespace.

    Existing output SVGs are returned as skips unless ``overwrite=True``.
    Explicit file inputs with unsupported extensions are reported as failures;
    unsupported files discovered inside directories are ignored.
    """

    _validate_mode(mode)
    _validate_embed_options(mode, embed_options)
    source_paths = tuple(Path(input_path) for input_path in input_paths)
    if not source_paths:
        raise InputPathError("At least one input file or directory is required.")

    destination_directory = Path(output_dir) if output_dir is not None else None
    if destination_directory is not None:
        _validate_output_directory(destination_directory)

    directory_inputs = tuple(path for path in source_paths if path.is_dir())
    prefix_directories = len(directory_inputs) > 1
    candidates: list[tuple[Path, Path]] = []
    initial_failures: list[ConversionFailure] = []
    for source in source_paths:
        if source.is_dir():
            directory_output = (
                source if destination_directory is None else destination_directory
            )
            if destination_directory is not None and prefix_directories:
                directory_output = destination_directory / source.name
            candidates.extend(
                _directory_candidates(source, directory_output, recursive=recursive)
            )
            continue

        destination = (
            source.with_suffix(".svg")
            if destination_directory is None
            else destination_directory / source.with_suffix(".svg").name
        )
        if not source.exists():
            initial_failures.append(
                ConversionFailure(
                    input_path=source,
                    error=InputPathError(f"Input file does not exist: {source}"),
                )
            )
            continue
        candidates.append((source, destination))

    return _convert_candidates(
        candidates,
        overwrite=overwrite,
        mode=mode,
        vectorize_options=vectorize_options,
        embed_options=embed_options,
        initial_failures=initial_failures,
    )


class SVGConverter:
    """Configurable facade for repeated embedding or vectorization operations."""

    def __init__(
        self,
        *,
        overwrite: bool = False,
        recursive: bool = False,
        mode: ConversionMode = "embed",
        vectorize_options: VectorizeOptions | None = None,
        embed_options: EmbedOptions | None = None,
    ) -> None:
        _validate_mode(mode)
        _validate_embed_options(mode, embed_options)
        self.overwrite = overwrite
        self.recursive = recursive
        self.mode = mode
        self.vectorize_options = vectorize_options
        self.embed_options = embed_options

    def convert_file(
        self, input_path: str | Path, output_path: str | Path | None = None
    ) -> Path:
        """Convert one image using this instance's configuration."""

        return convert_file(
            input_path,
            output_path,
            overwrite=self.overwrite,
            mode=self.mode,
            vectorize_options=self.vectorize_options,
            embed_options=self.embed_options,
        )

    def convert_directory(
        self,
        directory: str | Path,
        output_dir: str | Path | None = None,
        *,
        recursive: bool | None = None,
    ) -> BatchResult:
        """Convert one directory using this instance's configuration."""

        return convert_directory(
            directory,
            output_dir,
            overwrite=self.overwrite,
            recursive=self.recursive if recursive is None else recursive,
            mode=self.mode,
            vectorize_options=self.vectorize_options,
            embed_options=self.embed_options,
        )

    def convert_paths(
        self,
        input_paths: Iterable[str | Path],
        output_dir: str | Path | None = None,
        *,
        recursive: bool | None = None,
    ) -> BatchResult:
        """Convert multiple files and directories using this configuration."""

        return convert_paths(
            input_paths,
            output_dir,
            overwrite=self.overwrite,
            recursive=self.recursive if recursive is None else recursive,
            mode=self.mode,
            vectorize_options=self.vectorize_options,
            embed_options=self.embed_options,
        )
