"""High-level image conversion API.

The ``embed`` mode deliberately stores source raster bytes in an SVG ``<image>``
element. It does not turn pixels into vector paths; ``vectorize`` provides that
separate optional mode.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

from .batch import (
    convert_candidates,
    directory_candidates,
    path_candidates,
    validate_output_directory,
)
from .embed import embed_image, validate_input
from .errors import (
    ConversionError,
    InputPathError,
    OutputCollisionError,
    OutputExistsError,
    SVGConverterError,
    UnsupportedImageError,
    VectorizationDependencyError,
)
from .models import (
    BatchResult,
    CancelCallback,
    ConversionFailure,
    ConversionMetrics,
    ConversionMode,
    ConversionProgress,
    ConversionSkip,
    EmbedOptions,
    ProgressCallback,
    VectorizeColorMode,
    VectorizeCurveMode,
    VectorizeHierarchy,
    VectorizeOptions,
)
from .paths import ensure_within_root, resolve_allowed_root
from .vectorize import vectorize_image

__all__ = [
    "BatchResult",
    "CancelCallback",
    "ConversionError",
    "ConversionFailure",
    "ConversionMetrics",
    "ConversionMode",
    "ConversionProgress",
    "ConversionSkip",
    "EmbedOptions",
    "InputPathError",
    "OutputCollisionError",
    "OutputExistsError",
    "ProgressCallback",
    "SVGConverter",
    "SVGConverterError",
    "UnsupportedImageError",
    "VectorizationDependencyError",
    "VectorizeColorMode",
    "VectorizeCurveMode",
    "VectorizeHierarchy",
    "VectorizeOptions",
    "convert_directory",
    "convert_file",
    "convert_file_with_metrics",
    "convert_paths",
]


def _validate_mode(mode: ConversionMode) -> None:
    if mode not in ("embed", "vectorize"):
        raise ValueError("mode must be either 'embed' or 'vectorize'.")


def _validate_embed_options(
    mode: ConversionMode, embed_options: EmbedOptions | None
) -> None:
    if mode == "vectorize" and embed_options is not None and embed_options.is_enabled:
        raise ValueError("embed_options can only be used with mode='embed'.")


def _temporary_output_path(destination: Path) -> Path:
    """Create a closed temporary output file beside the final destination."""

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.stem}-",
        suffix=".svg.tmp",
        dir=destination.parent,
    )
    try:
        os.close(file_descriptor)
    except OSError:
        try:
            Path(temporary_name).unlink()
        except OSError:
            pass
        raise
    return Path(temporary_name)


def _validate_temporary_output(temporary_path: Path, destination: Path) -> None:
    """Ensure a staged SVG exists, is non-empty, and can be read."""

    try:
        if not temporary_path.is_file():
            raise ConversionError(
                f"Conversion did not create an SVG for destination {destination}."
            )
        if temporary_path.stat().st_size == 0:
            raise ConversionError(
                f"Conversion produced an empty SVG for destination {destination}."
            )
        with temporary_path.open("rb") as output:
            if not output.read(1):
                raise ConversionError(
                    f"Conversion produced an unreadable SVG for destination "
                    f"{destination}."
                )
    except OSError as error:
        raise ConversionError(
            f"Cannot validate SVG output for destination {destination}: {error}"
        ) from error


def _cleanup_temporary_output(temporary_path: Path | None) -> None:
    """Remove a staged output without hiding the original conversion error."""

    if temporary_path is None:
        return
    try:
        temporary_path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def convert_file_with_metrics(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    overwrite: bool = False,
    mode: ConversionMode = "embed",
    vectorize_options: VectorizeOptions | None = None,
    embed_options: EmbedOptions | None = None,
    allowed_root: str | Path | None = None,
) -> ConversionMetrics:
    """Convert one image and return the result path plus byte-size metrics.

    ``output_path`` defaults to the input filename with an ``.svg`` suffix.
    Parent directories for an explicit output path are created automatically.
    Existing outputs are preserved unless ``overwrite=True`` is provided.

    ``mode="embed"`` stores the original raster bytes in an SVG ``<image>``
    element unless enabled ``embed_options`` request preprocessing. ``mode="vectorize"``
    traces the image into vector paths and requires the ``vectorize`` optional
    dependency.

    When ``allowed_root`` is provided, resolved input and output paths must stay
    inside that directory; this is useful when paths come from an untrusted
    integration. The default ``None`` preserves the local CLI/library behavior.
    """

    _validate_mode(mode)
    _validate_embed_options(mode, embed_options)
    path_root = resolve_allowed_root(allowed_root)
    source = ensure_within_root(input_path, path_root, label="Input path")
    validate_input(source)
    destination = (
        ensure_within_root(output_path, path_root, label="Output path")
        if output_path is not None
        else source.with_suffix(".svg")
    )

    if destination.exists() and not overwrite:
        raise OutputExistsError(
            f"Output already exists: {destination}. Pass overwrite=True to replace it."
        )
    if destination.exists() and destination.is_dir():
        raise InputPathError(f"Output path is a directory: {destination}")

    temporary_output: Path | None = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        staged_output = _temporary_output_path(destination)
        temporary_output = staged_output
        if mode == "embed":
            embedded_raster_bytes = embed_image(source, staged_output, embed_options)
        else:
            vectorize_image(
                source, staged_output, vectorize_options or VectorizeOptions()
            )
            embedded_raster_bytes = None
        _validate_temporary_output(staged_output, destination)
        if destination.exists() and not overwrite:
            raise OutputExistsError(
                f"Output appeared during conversion: {destination}. "
                "Pass overwrite=True to replace it."
            )
        if destination.exists() and destination.is_dir():
            raise InputPathError(f"Output path is a directory: {destination}")
        os.replace(staged_output, destination)
        temporary_output = None
        return ConversionMetrics(
            input_path=source,
            output_path=destination,
            input_bytes=source.stat().st_size,
            svg_bytes=destination.stat().st_size,
            embedded_raster_bytes=embedded_raster_bytes,
        )
    except ConversionError as error:
        raise ConversionError(
            f"Conversion failed for {source} -> {destination}: {error}"
        ) from error
    except OSError as error:
        raise ConversionError(
            f"Cannot write SVG {destination} for input {source}: {error}"
        ) from error
    finally:
        _cleanup_temporary_output(temporary_output)


def convert_file(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    overwrite: bool = False,
    mode: ConversionMode = "embed",
    vectorize_options: VectorizeOptions | None = None,
    embed_options: EmbedOptions | None = None,
    allowed_root: str | Path | None = None,
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
        allowed_root=allowed_root,
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
    allowed_root: str | Path | None = None,
    progress_callback: ProgressCallback | None = None,
    should_cancel: CancelCallback | None = None,
) -> BatchResult:
    """Convert supported images in one directory, optionally including children.

    Files with non-image extensions are ignored. Each supported image is
    attempted independently, so a corrupt image does not stop the batch. When
    ``recursive=True`` and ``output_dir`` is supplied, the output mirrors the
    source directory structure. Existing SVGs are skipped unless
    ``overwrite=True`` is supplied. ``progress_callback`` is called after each
    processed input, while ``should_cancel`` can stop before the next input.

    Pass ``allowed_root`` to keep resolved input and output paths inside a
    trusted directory when the directory path comes from an untrusted source.
    """

    _validate_mode(mode)
    _validate_embed_options(mode, embed_options)
    path_root = resolve_allowed_root(allowed_root)
    source_directory = ensure_within_root(directory, path_root, label="Input directory")
    if not source_directory.exists():
        raise InputPathError(f"Input directory does not exist: {source_directory}")
    if not source_directory.is_dir():
        raise InputPathError(f"Input path is not a directory: {source_directory}")

    destination_directory = (
        ensure_within_root(output_dir, path_root, label="Output directory")
        if output_dir is not None
        else source_directory
    )
    validate_output_directory(destination_directory)
    return convert_candidates(
        directory_candidates(
            source_directory, destination_directory, recursive=recursive
        ),
        convert_file=convert_file_with_metrics,
        overwrite=overwrite,
        mode=mode,
        vectorize_options=vectorize_options,
        embed_options=embed_options,
        allowed_root=path_root,
        progress_callback=progress_callback,
        should_cancel=should_cancel,
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
    allowed_root: str | Path | None = None,
    progress_callback: ProgressCallback | None = None,
    should_cancel: CancelCallback | None = None,
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

    Pass ``allowed_root`` to confine every resolved input and output path to a
    trusted directory when batch paths come from an untrusted integration.

    ``progress_callback`` is called after each processed input. Return ``True``
    from ``should_cancel`` to finish the current item and stop before the next;
    the returned result then has ``cancelled=True``.
    """

    _validate_mode(mode)
    _validate_embed_options(mode, embed_options)
    candidates, initial_failures = path_candidates(
        input_paths,
        output_dir,
        recursive=recursive,
        allowed_root=allowed_root,
    )
    return convert_candidates(
        candidates,
        convert_file=convert_file_with_metrics,
        overwrite=overwrite,
        mode=mode,
        vectorize_options=vectorize_options,
        embed_options=embed_options,
        allowed_root=allowed_root,
        progress_callback=progress_callback,
        should_cancel=should_cancel,
        initial_failures=initial_failures,
    )


class SVGConverter:
    """Configurable facade for repeated conversion operations.

    ``allowed_root`` optionally confines resolved input and output paths to a
    trusted directory for integrations that accept untrusted path values.
    """

    def __init__(
        self,
        *,
        overwrite: bool = False,
        recursive: bool = False,
        mode: ConversionMode = "embed",
        vectorize_options: VectorizeOptions | None = None,
        embed_options: EmbedOptions | None = None,
        allowed_root: str | Path | None = None,
    ) -> None:
        _validate_mode(mode)
        _validate_embed_options(mode, embed_options)
        self.overwrite = overwrite
        self.recursive = recursive
        self.mode: ConversionMode = mode
        self.vectorize_options = vectorize_options
        self.embed_options = embed_options
        self.allowed_root: Path | None = resolve_allowed_root(allowed_root)

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
            allowed_root=self.allowed_root,
        )

    def convert_directory(
        self,
        directory: str | Path,
        output_dir: str | Path | None = None,
        *,
        recursive: bool | None = None,
        progress_callback: ProgressCallback | None = None,
        should_cancel: CancelCallback | None = None,
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
            allowed_root=self.allowed_root,
            progress_callback=progress_callback,
            should_cancel=should_cancel,
        )

    def convert_paths(
        self,
        input_paths: Iterable[str | Path],
        output_dir: str | Path | None = None,
        *,
        recursive: bool | None = None,
        progress_callback: ProgressCallback | None = None,
        should_cancel: CancelCallback | None = None,
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
            allowed_root=self.allowed_root,
            progress_callback=progress_callback,
            should_cancel=should_cancel,
        )
